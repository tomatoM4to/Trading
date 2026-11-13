import asyncio
import socket
import sqlite3
import subprocess
import sys
from fractions import Fraction

import pytest
import requests
from core import database

from tests.support import ROOT

pytestmark = pytest.mark.stage1


@pytest.mark.parametrize("prefix", ["ma", "ma_daily_"])
def test_ma_identifier_whitelist_is_closed_over_numeric_periods(prefix):
    from services.screener_service import ScreenerEngine

    engine = ScreenerEngine()
    for period in range(1, 251):
        line = f"{prefix}{period}"
        if period in (5, 10, 20, 60, 120, 200):
            assert engine._validate_ma_line(line) == f"ma{period}"
        else:
            with pytest.raises(ValueError):
                engine._validate_ma_line(line)


def test_every_ma_window_and_ticker_timeframe_independence():
    from core.ma_calculator import MACalculator

    calc = MACalculator()
    prices = [80 + i * 17 % 43 for i in range(430)]
    for index, close in enumerate(prices):
        calc.add_daily_close("A", close)
        calc.add_minute_close("B", close * 3)
        expected = {
            f"ma{period}": round(
                float(Fraction(sum(prices[index - period + 1 : index + 1]), period)), 2
            )
            if index + 1 >= period
            else None
            for period in (5, 10, 20, 60, 120, 200)
        }
        assert calc.get_daily_ma("A") == expected
        assert calc.get_minute_ma("A") == dict.fromkeys(expected)
        for key, value in expected.items():
            actual = calc.get_minute_ma("B")[key]
            if value is None:
                assert actual is None
            else:
                period = int(key[2:])
                assert actual == round(
                    float(
                        Fraction(
                            sum(prices[index - period + 1 : index + 1]) * 3, period
                        )
                    ),
                    2,
                )
    calc.clear()
    assert all(v is None for v in calc.get_daily_ma("A").values())


def test_strict_upsert_keys_and_rollback():
    conn = database.connect_sqlite()
    try:
        original = ("A", 20261112, 100, 110, 90, 105, 7, 735)
        conn.execute("INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)", original)
        conn.commit()
        conn.execute(
            "INSERT OR REPLACE INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)",
            ("A", 20261112, 100, 111, 90, 106, 8, 848),
        )
        conn.rollback()
        assert tuple(conn.execute("SELECT * FROM daily_ohlcv").fetchone()) == original
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)",
                ("B", "bad-date", 1, 1, 1, 1, 1, 1),
            )
    finally:
        conn.close()


async def test_disk_ma_and_thread_context_are_isolated(sandbox):
    sandbox.stock()

    def read():
        conn = database.connect_sqlite()
        try:
            return (
                conn.execute("PRAGMA database_list").fetchone()[2],
                conn.execute("SELECT ticker FROM stock_codes").fetchone()[0],
            )
        finally:
            conn.close()

    path, ticker = await asyncio.to_thread(read)
    assert path == str(sandbox.disk)
    assert ticker == "A"
    conn = database.connect_ma_db()
    try:
        assert conn.execute("PRAGMA database_list").fetchone()[2] == ""
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("SELECT * FROM daily_ohlcv")
    finally:
        conn.close()


def test_guard_rejects_outside_db_and_attach(offline):
    count = len(offline.blocked)
    with pytest.raises(AssertionError):
        sqlite3.connect("file:ma_db?mode=memory&cache=shared", uri=True)
    assert len(offline.blocked) == count + 1
    offline.blocked.pop()
    conn = database.connect_sqlite()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(
                "ATTACH DATABASE 'file:ma_db?mode=memory&cache=shared' AS unsafe"
            )
    finally:
        conn.close()


def test_support_import_does_not_patch_process_state():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import builtins, logging, os, socket, sqlite3, sys, requests; "
            "before = (builtins.open, sqlite3.connect, socket.socket.connect, "
            "requests.Session.request, os.getcwd(), list(sys.path), logging.root.manager.disable); "
            "import tests.support; "
            "assert before == (builtins.open, sqlite3.connect, socket.socket.connect, "
            "requests.Session.request, os.getcwd(), list(sys.path), logging.root.manager.disable); "
            "assert 'core.kis_auth' not in sys.modules",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_guard_blocks_http_and_socket_before_transport(offline):
    count = len(offline.blocked)
    with pytest.raises(AssertionError, match="blocked network"):
        requests.get("https://fixture.invalid")
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="blocked network"):
            connection.connect(("127.0.0.1", 1))
    with pytest.raises(AssertionError, match="blocked network"):
        socket.create_connection(("127.0.0.1", 1))
    assert offline.blocked[count:] == ["network"] * 3
    del offline.blocked[count:]
