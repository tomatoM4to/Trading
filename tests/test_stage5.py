import asyncio
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import pytest
from core import database

from tests.data import daily_series, ma_reference, minute_series
from tests.support import ROOT, FrozenDateTime, load_fixture
from tests.transport import FakeTransport, response

pytestmark = pytest.mark.stage5


@pytest.mark.parametrize("debug", ["True", "False"])
@pytest.mark.parametrize("sched", ["True", "False"])
async def test_initial_auth_failure_aborts_lifespan_and_cleans_queue(
    sandbox, debug, sched
):
    import os

    from core import kis_auth, kis_fetch
    from main import app, lifespan

    baseline = asyncio.all_tasks()
    with (
        patch.dict(os.environ, {"DEBUG": debug, "SCHED": sched}),
        patch("main.init_sqlite_connection") as init_db,
        patch.object(kis_auth, "config_root", sandbox.path / "tokens"),
        patch.object(kis_auth, "_kis_env", None),
        patch("main.SystemScheduler.start") as scheduler,
        patch("core.bootstrap.run_bootstrap_pipeline") as bootstrap,
        patch("core.bootstrap.rebuild_ma_database") as rebuild,
        FakeTransport([response(status=401)]),
    ):
        with pytest.raises(RuntimeError):
            async with lifespan(app):
                pytest.fail("Unauthenticated application reached serving state")
        assert kis_fetch._kis_worker_task is None
        assert kis_fetch._kis_queue is None
        assert asyncio.all_tasks() == baseline
        init_db.assert_not_called()
        scheduler.assert_not_called()
        bootstrap.assert_not_called()
        rebuild.assert_not_called()


async def test_start_failure_after_queue_creation_stops_owned_worker(sandbox):
    import os

    from core import kis_fetch
    from main import app, lifespan

    baseline = asyncio.all_tasks()
    with (
        patch.dict(os.environ, {"SCHED": "True"}),
        patch("main.init_sqlite_connection"),
        patch("core.kis_auth.auth"),
        patch(
            "main.SystemScheduler.start", side_effect=RuntimeError("scheduler failed")
        ),
        patch("main.SystemScheduler.stop") as stop,
    ):
        with pytest.raises(RuntimeError, match="scheduler failed"):
            async with lifespan(app):
                pytest.fail("Failed startup reached serving state")
        assert kis_fetch._kis_worker_task is None
        assert kis_fetch._kis_queue is None
        assert asyncio.all_tasks() == baseline
        stop.assert_called_once()


async def test_bootstrap_and_scheduled_minute_start_share_one_collector(sandbox):
    from core.scheduler import SystemScheduler

    from tasks import minute_ohlcv_scheduler as minute

    entered = asyncio.Event()
    collectors = []

    async def collect(markets=None):
        collectors.append(asyncio.current_task())
        entered.set()
        await asyncio.Event().wait()

    with (
        patch.object(minute, "_running_minute_scheduler_task", None),
        patch.object(minute, "run_minute_ohlcv_scheduler", collect),
    ):
        scheduled = None
        try:
            await minute.start_minute_scheduler_task()
            await asyncio.wait_for(entered.wait(), 2)
            scheduled = asyncio.create_task(
                SystemScheduler().start_minute_scheduler_job()
            )
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert len(collectors) == 1
            scheduled.cancel()
            await asyncio.gather(scheduled, return_exceptions=True)
            assert not collectors[0].done()
            await minute.start_minute_scheduler_task()
            await asyncio.sleep(0)
            assert len(collectors) == 1
        finally:
            tasks = [*collectors, *([scheduled] if scheduled else [])]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def test_minute_stop_drains_cleanup_despite_cancelled_and_repeated_callers():
    from tasks import minute_ohlcv_scheduler as minute

    entered, cleaning, release, finished = (asyncio.Event() for _ in range(4))

    async def collect(markets=None):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await release.wait()
            finished.set()

    with (
        patch.object(minute, "_running_minute_scheduler_task", None),
        patch.object(minute, "run_minute_ohlcv_scheduler", collect),
    ):
        collector = await minute.start_minute_scheduler_task()
        stops = []
        try:
            await asyncio.wait_for(entered.wait(), 2)
            stops.append(asyncio.create_task(minute.stop_minute_scheduler_task()))
            await asyncio.wait_for(cleaning.wait(), 2)
            stops.append(asyncio.create_task(minute.stop_minute_scheduler_task()))
            stops[0].cancel()
            await asyncio.sleep(0)
            assert all(not task.done() for task in stops)
            assert not collector.done()
            assert await minute.start_minute_scheduler_task() is collector
            release.set()
            await asyncio.wait_for(asyncio.gather(*stops, return_exceptions=True), 2)
            assert stops[0].cancelled()
            assert stops[1].result() is None
            assert finished.is_set()
            assert collector.cancelled()
            assert minute._running_minute_scheduler_task is None
            restarted = await minute.start_minute_scheduler_task()
            assert restarted is not collector
            await minute.stop_minute_scheduler_task()
            assert restarted.done()
        finally:
            release.set()
            await minute.stop_minute_scheduler_task()
            await asyncio.gather(*stops, return_exceptions=True)


async def test_background_minute_failure_is_reported_and_can_restart():
    from tasks import minute_ohlcv_scheduler as minute

    error = RuntimeError("minute collection failed")

    async def fail(markets=None):
        raise error

    with (
        patch.object(minute, "_running_minute_scheduler_task", None),
        patch.object(minute, "run_minute_ohlcv_scheduler", fail),
        patch.object(minute.logger, "error") as log,
    ):
        failed = await minute.start_minute_scheduler_task()
        await asyncio.wait({failed})
        log.assert_called_once_with("Minute OHLCV collector failed: %s", error)
        assert minute._running_minute_scheduler_task is None
        restarted = await minute.start_minute_scheduler_task()
        assert restarted is not failed
        await minute.stop_minute_scheduler_task()
        assert restarted.done()


@pytest.mark.parametrize("serving_failure", [False, True])
@pytest.mark.parametrize("cancel_shutdown", [False, True])
async def test_lifespan_stops_bootstrap_minute_workers_before_kis_queue(
    sandbox, serving_failure, cancel_shutdown
):
    import os
    import threading

    from core import bootstrap, kis_fetch
    from main import app, lifespan

    from tasks import minute_ohlcv_scheduler as minute

    sandbox.stock()
    baseline = asyncio.all_tasks()
    gate = threading.Event()
    queue_stopping = asyncio.Event()
    stopped_collectors = []
    stop_queue = kis_fetch.stop_q_worker

    async def stop_observed_queue():
        stopped_collectors.append(collector.done())
        queue_stopping.set()
        await stop_queue()

    with (
        patch.dict(os.environ, {"SCHED": "True"}),
        patch("main.init_sqlite_connection"),
        patch("core.kis_auth.auth"),
        patch("main.SystemScheduler.start"),
        patch("main.SystemScheduler.stop"),
        patch.object(bootstrap, "run_daily_ohlcv_scheduler"),
        patch.object(bootstrap, "rebuild_ma_database"),
        patch.object(minute, "_running_minute_scheduler_task", None),
        patch("main.stop_q_worker", stop_observed_queue),
        FakeTransport([response([])], gate=gate) as transport,
    ):
        context = lifespan(app)
        closing = None
        collector = None
        try:
            await context.__aenter__()
            assert await asyncio.to_thread(transport.entered.wait, 2)
            collector = minute._running_minute_scheduler_task
            error = RuntimeError("serving failed") if serving_failure else None
            closing = asyncio.create_task(
                context.__aexit__(type(error) if error else None, error, None)
            )
            await asyncio.wait_for(queue_stopping.wait(), 2)
            assert stopped_collectors == [True]
            if cancel_shutdown:
                closing.cancel()
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                assert not closing.done()
            gate.set()
            await asyncio.wait_for(asyncio.gather(closing, return_exceptions=True), 2)
            if cancel_shutdown:
                assert closing.cancelled()
            else:
                closing.result()
            assert collector.done()
            assert kis_fetch._kis_queue is None
            assert kis_fetch._kis_worker_task is None
            assert asyncio.all_tasks() == baseline
        finally:
            gate.set()
            if collector is not None:
                if not collector.done():
                    collector.cancel()
                await asyncio.gather(collector, return_exceptions=True)
            if closing is not None:
                await asyncio.gather(closing, return_exceptions=True)
            await stop_queue()


@contextmanager
def deny_sqlite_read(module, table, column=None):
    connect = module.connect_sqlite
    denied = []

    def connect_with_failure():
        conn = connect()

        def authorize(action, name, field, db, trigger):
            if action == sqlite3.SQLITE_READ and name == table:
                if column is None or field == column:
                    denied.append((name, field))
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorize)
        return conn

    with patch.object(module, "connect_sqlite", connect_with_failure):
        yield denied


def test_minute_last_times_distinguishes_empty_and_existing_data(sandbox):
    from tasks.minute_ohlcv_scheduler import get_minute_last_times

    assert get_minute_last_times() == {}
    sandbox.stock()
    rows = minute_series(400)
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?,?)",
        list(reversed(rows)),
    )
    assert get_minute_last_times(["KOSPI"]) == {"A": "20261110090800"}
    assert get_minute_last_times(["KOSDAQ"]) == {}


@pytest.mark.parametrize(
    ("mode", "table", "column"),
    [
        ("daily", "stock_codes", "ticker"),
        ("daily", "daily_ohlcv", "date"),
        ("minute", "minute_ohlcv", "date"),
        ("minute", "stock_codes", "is_halted"),
    ],
)
async def test_collector_initial_select_failure_reaches_scheduler_without_kis_calls(
    sandbox, mode, table, column
):
    from core.scheduler import SystemScheduler
    from core.state import system_state

    from tasks import daily_ohlcv_scheduler as daily
    from tasks import minute_ohlcv_scheduler as minute

    sandbox.stock()
    module = daily if mode == "daily" else minute
    job = (
        SystemScheduler().run_daily_ohlcv_job
        if mode == "daily"
        else SystemScheduler().start_minute_scheduler_job
    )
    with (
        deny_sqlite_read(module, table, column) as denied,
        FakeTransport([]) as transport,
        patch("core.scheduler.logger") as log,
        patch("core.database.sync_memory_to_disk") as checkpoint,
    ):
        with pytest.raises(sqlite3.DatabaseError):
            await asyncio.wait_for(job(), 2)
        assert denied
        assert transport.calls == []
        log.error.assert_called_once()
        assert not any(
            "completed" in str(c) or "finished naturally" in str(c)
            for c in log.sched.call_args_list
        )
        checkpoint.assert_not_called()
    assert system_state.status == (True, "")


async def test_minute_last_times_select_failure_is_not_empty(sandbox):
    from tasks import minute_ohlcv_scheduler as minute

    with deny_sqlite_read(minute, "minute_ohlcv", "date") as denied:
        with pytest.raises(sqlite3.DatabaseError):
            minute.get_minute_last_times()
        assert denied


@pytest.mark.parametrize("mode", ["daily", "minute"])
async def test_empty_market_is_successful_without_kis_calls(sandbox, mode):
    from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
    from tasks.minute_ohlcv_scheduler import run_minute_ohlcv_scheduler

    with FakeTransport([]) as transport:
        if mode == "daily":
            await run_daily_ohlcv_scheduler()
        else:
            await run_minute_ohlcv_scheduler(single_cycle=True)
        assert transport.calls == []


@pytest.mark.parametrize("table", ["sqlite_master", "stock_codes", "daily_ohlcv"])
async def test_bootstrap_presence_select_failure_stops_all_later_work(sandbox, table):
    from core import bootstrap

    sandbox.stock()
    with (
        deny_sqlite_read(bootstrap, table) as denied,
        FakeTransport([]) as transport,
        patch.object(bootstrap, "init_stock_codes_db") as master,
        patch.object(bootstrap, "run_daily_ohlcv_scheduler") as daily,
        patch.object(bootstrap, "rebuild_ma_database") as rebuild,
        patch("tasks.minute_ohlcv_scheduler.start_minute_scheduler_task") as minute,
    ):
        with pytest.raises(sqlite3.DatabaseError):
            await bootstrap.run_bootstrap_pipeline()
        assert denied
        assert transport.calls == []
        master.assert_not_called()
        daily.assert_not_called()
        rebuild.assert_not_called()
        minute.assert_not_called()


async def test_bootstrap_empty_database_follows_normal_initialization(sandbox):
    from core import bootstrap

    with (
        patch.object(
            bootstrap, "init_stock_codes_db", side_effect=sandbox.stock
        ) as master,
        patch.object(bootstrap, "run_daily_ohlcv_scheduler") as daily,
        patch("tasks.minute_ohlcv_scheduler.start_minute_scheduler_task") as minute,
        FakeTransport([]) as transport,
    ):
        await bootstrap.run_bootstrap_pipeline()
        master.assert_called_once()
        assert [c.args for c in daily.call_args_list] == [("KOSPI",), ("KOSDAQ",)]
        assert all(c.kwargs == {"verify_history": True} for c in daily.call_args_list)
        minute.assert_awaited_once()
        assert transport.calls == []


async def test_minute_collector_reports_exhausted_db_retries(sandbox):
    from tasks import minute_ohlcv_scheduler as minute

    sandbox.stock()
    attempts = []
    rows = load_fixture("candles.json")["minute"]

    async def fetch(*args, **kwargs):
        import pandas as pd

        if not attempts:
            sandbox.write("DROP TABLE minute_ohlcv")
        attempts.append(args)
        return pd.DataFrame(rows)

    with patch.object(minute, "fetch_minute_data", fetch):
        with pytest.raises(
            RuntimeError, match="Minute collection failed for 1 tickers"
        ):
            await minute.run_minute_ohlcv_scheduler(single_cycle=True)
    assert len(attempts) == 4


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
