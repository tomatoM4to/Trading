import asyncio
import sqlite3
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

import pytest
from core import database

from tests.data import daily_series, ma_reference, minute_series
from tests.support import ROOT, FrozenDateTime, load_fixture
from tests.transport import FakeTransport, response

pytestmark = pytest.mark.stage5


@pytest.mark.parametrize("mode", ("daily", "minute"))
async def test_cancelled_collectors_leave_no_owned_workers_running(sandbox, mode):
    import threading

    from core import kis_fetch
    from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
    from tasks.minute_ohlcv_scheduler import run_minute_ohlcv_scheduler

    sandbox.stock()
    baseline = asyncio.all_tasks()
    gate = threading.Event()
    with FakeTransport([response([])], gate=gate) as transport:
        collector = asyncio.create_task(
            run_daily_ohlcv_scheduler()
            if mode == "daily"
            else run_minute_ohlcv_scheduler(single_cycle=True)
        )
        leaked = []
        try:
            assert await asyncio.to_thread(transport.entered.wait, 2)
            collector.cancel()
            await asyncio.gather(collector, return_exceptions=True)
            leaked = [
                t
                for t in asyncio.all_tasks() - baseline
                if t is not kis_fetch._kis_worker_task and (not t.done())
            ]
        finally:
            gate.set()
            for task in leaked:
                task.cancel()
            await asyncio.gather(*leaked, return_exceptions=True)
            await kis_fetch.stop_q_worker()
    assert len(leaked) == 0, f"{mode} collector left child workers alive"


async def test_rebuild_after_memory_loss_reconstructs_every_retained_ma(sandbox):
    from core.bootstrap import rebuild_ma_database

    daily, minute = (daily_series(500), minute_series(850))
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily)
    sandbox.write("INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", minute)
    database._keepalive_ma_conn.close()
    database.init_sqlite_connection()
    await rebuild_ma_database()
    assert sandbox.rows("daily_ma") == ma_reference(daily, retention=301)
    assert sandbox.rows("minute_ma") == ma_reference(minute, minute=True, retention=391)


async def test_crash_before_commit_rolls_back_whole_page(sandbox):
    child = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-m",
            "tests.crash_worker",
            str(sandbox.path),
            "mid-transaction",
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 23, child.stderr.decode(errors="replace")
    assert sandbox.rows("daily_ohlcv") == []
    conn = database.connect_sqlite()
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.execute("DROP TRIGGER crash_write")
    finally:
        conn.close()


async def test_crash_after_disk_commit_rebuilds_ma_from_canonical_records(sandbox):
    from core.bootstrap import rebuild_ma_database

    child = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "tests.crash_worker", str(sandbox.path), "after-commit"],
        cwd=ROOT,
        capture_output=True,
        timeout=15,
    )
    assert child.returncode == 23, child.stderr.decode(errors="replace")
    expected = [tuple(r) for r in load_fixture("candles.json")["daily_expected"]]
    assert sandbox.rows("daily_ohlcv") == expected
    await rebuild_ma_database()
    assert sandbox.rows("daily_ma") == ma_reference(expected)


async def test_wal_reader_snapshot_and_checkpoint_retry():
    row = daily_series(1)[0]
    reader, writer = (database.connect_sqlite(), database.connect_sqlite())
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0] == 0
        writer.execute("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", row)
        writer.commit()
        assert reader.execute("SELECT COUNT(*) FROM daily_ohlcv").fetchone()[0] == 0
        await asyncio.to_thread(database.sync_memory_to_disk)
        reader.rollback()
        assert tuple(reader.execute("SELECT * FROM daily_ohlcv").fetchone()) == row
        reader.close()
        await asyncio.to_thread(database.sync_memory_to_disk)
        assert writer.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reader.close()
        writer.close()


async def test_write_lock_failure_then_retry_does_not_partially_commit(sandbox):
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily_series(1))
    blocker, writer = (database.connect_sqlite(), database.connect_sqlite())
    try:
        blocker.execute("BEGIN IMMEDIATE")
        writer.execute("PRAGMA busy_timeout=10")
        with pytest.raises(sqlite3.OperationalError):
            writer.execute("UPDATE daily_ohlcv SET close=999")
        writer.rollback()
        blocker.rollback()
        writer.execute("UPDATE daily_ohlcv SET close=999")
        writer.commit()
        assert writer.execute("SELECT close FROM daily_ohlcv").fetchone()[0] == 999
    finally:
        blocker.close()
        writer.close()


async def test_minute_ma_failure_retry_cannot_skip_unbuilt_ma(sandbox):
    from tasks.minute_ohlcv_scheduler import process_ticker

    source = load_fixture("candles.json")
    ma = database.connect_ma_db()
    try:
        ma.execute(
            "CREATE TRIGGER reject_ma BEFORE INSERT ON minute_ma BEGIN SELECT RAISE(ABORT,'injected MA failure'); END"
        )
        ma.commit()
        with FakeTransport([response(source["minute"])]):
            success, newest = await process_ticker("A", max_steps=1)
        assert not success
        assert newest == "20261112090300"
        assert sandbox.rows("minute_ohlcv") == [
            tuple(r) for r in source["minute_expected"]
        ]
        ma.execute("DROP TRIGGER reject_ma")
        ma.commit()
        with FakeTransport([response(source["minute"])]):
            await process_ticker("A", last_datetime=newest, max_steps=1)
        assert sandbox.rows("minute_ma") == ma_reference(
            source["minute_expected"], minute=True
        )
    finally:
        ma.close()


async def test_bootstrap_rebuild_failure_is_visible_to_caller(sandbox):
    from core.bootstrap import rebuild_ma_database

    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily_series(5))
    ma = database.connect_ma_db()
    try:
        ma.execute(
            "CREATE TRIGGER reject_rebuild BEFORE INSERT ON daily_ma BEGIN SELECT RAISE(ABORT,'injected rebuild failure'); END"
        )
        ma.commit()
        with pytest.raises(sqlite3.IntegrityError):
            await rebuild_ma_database()
    finally:
        ma.close()


async def test_system_guard_releases_on_failure_and_health_remains_available():
    from core.state import system_state
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    try:
        with system_state.acquire("outer"):
            with system_state.acquire("inner"):
                assert client.get("/health").status_code == 200
                assert client.get("/market/chart/A").status_code == 503
            assert system_state.status == (False, "outer")
            raise ValueError("injected")
    except ValueError:
        pass
    assert system_state.status == (True, "")
    assert client.get("/market/chart/A").status_code == 200


async def test_gc_preserves_latest_500_daily_and_two_minute_dates_per_ticker(sandbox):
    from core.scheduler import SystemScheduler

    yesterday = FrozenDateTime.now() - timedelta(days=1)
    for ticker in ("A", "B"):
        daily = daily_series(505, ticker, end_date=yesterday)
        minute = minute_series(1173, ticker)
        sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily)
        sandbox.write("INSERT INTO minute_ohlcv VALUES (?,?,?,?,?,?,?,?,?)", minute)
    with patch("core.scheduler.datetime", FrozenDateTime):
        await SystemScheduler().cleanup_ohlcv_job()
    expected_daily, expected_minute = ([], [])
    for ticker in ("A", "B"):
        daily = daily_series(505, ticker, end_date=yesterday)
        expected_daily.extend(sorted(daily, key=lambda r: r[1])[-500:])
        expected_minute.extend(minute_series(1173, ticker)[391:])
    assert sandbox.rows("daily_ohlcv") == expected_daily
    assert sandbox.rows("minute_ohlcv") == expected_minute
