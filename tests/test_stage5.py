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
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
        minute,
    )
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
        with (
            FakeTransport([response(source["minute"])]),
            pytest.raises(sqlite3.IntegrityError),
        ):
            await process_ticker("A", max_steps=1)
        assert sandbox.rows("minute_ohlcv") == [
            tuple(r) for r in source["minute_expected"]
        ]
        ma.execute("DROP TRIGGER reject_ma")
        ma.commit()
        with FakeTransport([response(source["minute"])]):
            await process_ticker("A", last_datetime="20261112090300", max_steps=1)
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


async def test_later_minute_page_failure_marks_committed_data_unready(sandbox):
    from core.bootstrap import rebuild_ma_database
    from core.state import system_state
    from tasks.minute_ohlcv_scheduler import process_ticker

    from tests.data import minute_wire

    rows = minute_series(10)
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    await rebuild_ma_database()
    changed = list(rows[-1])
    changed[6] += 10
    rows[-1] = tuple(changed)
    with (
        FakeTransport([response(minute_wire(rows)), response(status=500)]),
        pytest.raises(Exception, match="API Error"),
    ):
        await process_ticker("A", max_steps=2)
    assert not system_state.ma_status[0]
    assert sandbox.rows("minute_ohlcv") == rows
    with FakeTransport([response(minute_wire(rows))]):
        await process_ticker("A", max_steps=1)
    assert system_state.ma_status[0]
    assert sandbox.rows("minute_ma") == ma_reference(rows, minute=True)


async def test_full_rebuild_cannot_clear_a_newer_ticker_failure(sandbox):
    import threading

    from core.bootstrap import rebuild_ma_database
    from core.ma_calculator import ma_calculator
    from core.state import system_state
    from tasks.minute_ohlcv_scheduler import process_ticker

    from tests.data import minute_wire

    rows = minute_series(10)
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    await rebuild_ma_database()
    entered, release = threading.Event(), threading.Event()
    original = ma_calculator.add_minute_close

    def pause_after_snapshot(ticker, close):
        if not entered.is_set():
            entered.set()
            if not release.wait(3):
                raise AssertionError("Test did not release MA rebuild")
        original(ticker, close)

    with patch.object(ma_calculator, "add_minute_close", pause_after_snapshot):
        rebuilding = asyncio.create_task(rebuild_ma_database())
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            changed = list(rows[-1])
            changed[6] += 10
            rows[-1] = tuple(changed)
            with (
                FakeTransport([response(minute_wire(rows))]),
                pytest.raises(sqlite3.OperationalError, match="locked"),
            ):
                await process_ticker("A", max_steps=1)
        finally:
            release.set()
            await rebuilding
    assert not system_state.ma_status[0]
    assert sandbox.rows("minute_ohlcv") == rows
    with FakeTransport([response(minute_wire(rows))]):
        await process_ticker("A", max_steps=1)
    assert system_state.ma_status[0]
    assert sandbox.rows("minute_ma") == ma_reference(rows, minute=True)


async def test_minute_collector_retries_ma_failure_before_advancing_watermark(sandbox):
    from tasks.minute_ohlcv_scheduler import run_minute_ohlcv_scheduler

    sandbox.stock()
    source = load_fixture("candles.json")
    ma = database.connect_ma_db()
    try:
        ma.execute(
            "CREATE TRIGGER reject_ma BEFORE INSERT ON minute_ma BEGIN SELECT RAISE(ABORT,'injected MA failure'); END"
        )
        ma.commit()

        def recover_ma(call):
            ma.execute("DROP TRIGGER reject_ma")
            ma.commit()
            return response(source["minute"])

        with FakeTransport(
            [
                response(source["minute"]),
                *[response([])] * 14,
                recover_ma,
                *[response([])] * 14,
            ]
        ) as transport:
            await run_minute_ohlcv_scheduler(single_cycle=True)
        assert len(transport.calls) == 30
        assert sandbox.rows("minute_ma") == ma_reference(
            source["minute_expected"], minute=True
        )
    finally:
        ma.close()


async def test_bootstrap_minute_failure_rolls_back_both_ma_tables(sandbox):
    from core.bootstrap import rebuild_ma_database

    daily, minute = daily_series(10), minute_series(10)
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily)
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
        minute,
    )
    await rebuild_ma_database()
    before_daily, before_minute = sandbox.rows("daily_ma"), sandbox.rows("minute_ma")
    sandbox.write("UPDATE daily_ohlcv SET close=close+10")
    ma = database.connect_ma_db()
    try:
        ma.execute(
            "CREATE TRIGGER reject_rebuild BEFORE INSERT ON minute_ma BEGIN SELECT RAISE(ABORT,'injected rebuild failure'); END"
        )
        ma.commit()
        with pytest.raises(sqlite3.IntegrityError):
            await rebuild_ma_database()
        assert sandbox.rows("daily_ma") == before_daily
        assert sandbox.rows("minute_ma") == before_minute
    finally:
        ma.close()


async def test_failed_ma_rebuild_blocks_only_screener_until_recovery(sandbox):
    from core.bootstrap import rebuild_ma_database
    from fastapi.testclient import TestClient
    from main import app

    sandbox.stock()
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily_series(10))
    await rebuild_ma_database()
    client = TestClient(app)
    payload = {
        "filters": [
            {
                "id": "a",
                "type": "ma_alignment",
                "params": {"lines": ["ma_daily_5", "ma_daily_10"]},
            }
        ]
    }
    assert client.post("/api/screener/run", json=payload).status_code == 200
    ma = database.connect_ma_db()
    try:
        ma.execute(
            "CREATE TRIGGER reject_ready BEFORE INSERT ON daily_ma BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
        ma.commit()
        with pytest.raises(sqlite3.IntegrityError):
            await rebuild_ma_database()
        assert client.get("/health").status_code == 200
        assert client.get("/market/chart/A").status_code == 200
        assert client.post("/api/screener/run", json=payload).status_code == 503
        ma.execute("DROP TRIGGER reject_ready")
        ma.commit()
        await rebuild_ma_database()
        assert client.post("/api/screener/run", json=payload).status_code == 200
    finally:
        ma.close()


@pytest.mark.parametrize("minute", [False, True], ids=["daily", "minute"])
async def test_ticker_ma_failures_block_until_every_failed_ticker_recovers(
    sandbox, minute
):
    from core.bootstrap import rebuild_ma_database
    from core.state import system_state
    from tasks.daily_ohlcv_scheduler import process_ticker as daily_process
    from tasks.minute_ohlcv_scheduler import process_ticker as minute_process

    from tests.data import daily_wire, minute_wire

    table = "minute_ma" if minute else "daily_ma"
    rows = {
        ticker: (minute_series(10, ticker) if minute else daily_series(10, ticker))
        for ticker in ("A", "B")
    }
    for source in rows.values():
        if minute:
            sandbox.write(
                "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
                source,
            )
        else:
            sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", source)
    await rebuild_ma_database()
    assert system_state.ma_status[0]
    ma = database.connect_ma_db()
    try:
        ma.execute(
            f"CREATE TRIGGER reject_ticker BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
        ma.commit()
        for ticker, source in rows.items():
            changed = list(source[-1])
            changed[6 if minute else 5] += 1
            source[-1] = tuple(changed)
            with (
                FakeTransport(
                    [response(minute_wire(source) if minute else daily_wire(source))]
                ),
                pytest.raises(sqlite3.IntegrityError),
            ):
                await (
                    minute_process(ticker, max_steps=1)
                    if minute
                    else daily_process(ticker, last_date=source[-1][1])
                )
            assert not system_state.ma_status[0]
        ma.execute("DROP TRIGGER reject_ticker")
        ma.commit()
        for index, (ticker, source) in enumerate(rows.items()):
            with FakeTransport(
                [response(minute_wire(source) if minute else daily_wire(source))]
            ):
                await (
                    minute_process(ticker, max_steps=1)
                    if minute
                    else daily_process(ticker, last_date=source[-1][1])
                )
            assert system_state.ma_status[0] is (index == 1)
        assert sandbox.rows(table) == sorted(
            row
            for source in rows.values()
            for row in ma_reference(source, minute=minute)
        )
    finally:
        ma.close()


@pytest.mark.parametrize("sched", ["True", "False"])
@pytest.mark.parametrize("fail", [True, False])
async def test_lifespan_cold_start_readiness_and_background_failure(
    sandbox, sched, fail
):
    import os
    import threading

    from core import bootstrap
    from core.state import system_state
    from httpx import ASGITransport, AsyncClient
    from main import app, lifespan

    sandbox.stock()
    sandbox.write("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", daily_series(10))
    entered, release = threading.Event(), threading.Event()
    rebuild = bootstrap._rebuild_ma_database

    def delayed_rebuild():
        entered.set()
        if not release.wait(3):
            raise AssertionError("Test did not release rebuild")
        if fail:
            raise RuntimeError("injected background failure")
        rebuild()

    async def collect_fixture(market, *, verify_history):
        assert verify_history

    async def start_minute_fixture():
        return True

    try:
        with (
            patch.dict(os.environ, {"SCHED": sched}),
            patch("main.init_sqlite_connection"),
            patch("core.kis_auth.auth"),
            patch("main.SystemScheduler.start"),
            patch("main.SystemScheduler.stop"),
            patch("core.bootstrap.run_daily_ohlcv_scheduler", collect_fixture),
            patch(
                "tasks.minute_ohlcv_scheduler.start_minute_scheduler_task",
                start_minute_fixture,
            ),
            patch("core.bootstrap._rebuild_ma_database", delayed_rebuild),
        ):
            async with lifespan(app):
                assert await asyncio.to_thread(entered.wait, 2)
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://fixture"
                ) as client:
                    payload = {
                        "filters": [
                            {
                                "id": "a",
                                "type": "ma_alignment",
                                "params": {"lines": ["ma_daily_5", "ma_daily_10"]},
                            }
                        ]
                    }
                    assert (await client.get("/health")).status_code == 200
                    assert (await client.get("/market/chart/A")).status_code == 200
                    assert (
                        await client.post("/api/screener/run", json=payload)
                    ).status_code == 503
                    release.set()
                    for _ in range(200):
                        ready, reason = system_state.ma_status
                        if ready or "실패" in reason:
                            break
                        await asyncio.sleep(0.01)
                    assert ready is not fail
                    assert (
                        await client.post("/api/screener/run", json=payload)
                    ).status_code == (503 if fail else 200)
    finally:
        release.set()


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
        sandbox.write(
            "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
            minute,
        )
    with patch("core.scheduler.datetime", FrozenDateTime):
        await SystemScheduler().cleanup_ohlcv_job()
    expected_daily, expected_minute = ([], [])
    for ticker in ("A", "B"):
        daily = daily_series(505, ticker, end_date=yesterday)
        expected_daily.extend(sorted(daily, key=lambda r: r[1])[-500:])
        expected_minute.extend(minute_series(1173, ticker)[391:])
    assert sandbox.rows("daily_ohlcv") == expected_daily
    assert sandbox.rows("minute_ohlcv") == expected_minute
