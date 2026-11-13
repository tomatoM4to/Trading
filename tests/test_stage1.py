import asyncio
import sqlite3
from fractions import Fraction

from tests.support import BLOCKED, DatabaseCase, database


class CalculationContracts(DatabaseCase):
    def test_ma_identifier_whitelist_is_closed_over_numeric_periods(self):
        from services.screener_service import ScreenerEngine

        engine = ScreenerEngine()
        for period in range(1, 251):
            for prefix in ("ma", "ma_daily_"):
                with self.subTest(period=period, prefix=prefix):
                    line = f"{prefix}{period}"
                    if period in (5, 10, 20, 60, 120, 200):
                        self.assertEqual(engine._validate_ma_line(line), f"ma{period}")
                    else:
                        with self.assertRaises(ValueError):
                            engine._validate_ma_line(line)

    def test_every_ma_window_and_ticker_timeframe_independence(self):
        from core.ma_calculator import MACalculator

        calc = MACalculator()
        prices = [80 + (i * 17) % 43 for i in range(430)]
        for index, close in enumerate(prices):
            calc.add_daily_close("A", close)
            calc.add_minute_close("B", close * 3)
            expected = {
                f"ma{period}": round(
                    float(
                        Fraction(sum(prices[index - period + 1 : index + 1]), period)
                    ),
                    2,
                )
                if index + 1 >= period
                else None
                for period in (5, 10, 20, 60, 120, 200)
            }
            self.assertEqual(calc.get_daily_ma("A"), expected)
            self.assertEqual(calc.get_minute_ma("A"), dict.fromkeys(expected))
            for key, value in expected.items():
                actual = calc.get_minute_ma("B")[key]
                if value is None:
                    self.assertIsNone(actual)
                else:
                    period = int(key[2:])
                    self.assertEqual(
                        actual,
                        round(
                            float(
                                Fraction(
                                    sum(prices[index - period + 1 : index + 1]) * 3,
                                    period,
                                )
                            ),
                            2,
                        ),
                    )
        calc.clear()
        self.assertTrue(all(v is None for v in calc.get_daily_ma("A").values()))

    def test_strict_upsert_keys_and_rollback(self):
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
            self.assertEqual(
                tuple(conn.execute("SELECT * FROM daily_ohlcv").fetchone()), original
            )
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO daily_ohlcv VALUES (?,?,?,?,?,?,?,?)",
                    ("B", "bad-date", 1, 1, 1, 1, 1, 1),
                )
        finally:
            conn.close()

    async def test_disk_ma_and_thread_context_are_isolated(self):
        self.box.stock()

        def read():
            conn = database.connect_sqlite()
            try:
                return conn.execute("PRAGMA database_list").fetchone()[2], conn.execute(
                    "SELECT ticker FROM stock_codes"
                ).fetchone()[0]
            finally:
                conn.close()

        path, ticker = await asyncio.to_thread(read)
        self.assertEqual(path, str(self.box.disk))
        self.assertEqual(ticker, "A")
        conn = database.connect_ma_db()
        try:
            self.assertEqual(conn.execute("PRAGMA database_list").fetchone()[2], "")
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("SELECT * FROM daily_ohlcv")
        finally:
            conn.close()

    def test_guard_rejects_outside_db_and_attach(self):
        count = len(BLOCKED)
        with self.assertRaises(AssertionError):
            sqlite3.connect("file:ma_db?mode=memory&cache=shared", uri=True)
        self.assertEqual(len(BLOCKED), count + 1)
        BLOCKED.pop()
        conn = database.connect_sqlite()
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                conn.execute(
                    "ATTACH DATABASE 'file:ma_db?mode=memory&cache=shared' AS unsafe"
                )
        finally:
            conn.close()
