import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


class ScreenerInputValidationTests(unittest.TestCase):
    def setUp(self):
        from services.screener_service import ScreenerEngine

        self.engine = ScreenerEngine()

    def test_ma_lines_reject_mixed_timeframes(self):
        with self.assertRaises(ValueError):
            self.engine._validate_ma_lines(["ma_daily_5", "ma20"])

    def test_ma_lines_reject_duplicate_periods(self):
        with self.assertRaises(ValueError):
            self.engine._validate_ma_lines(["ma_daily_20", "ma_daily_20"])

    def test_ma_cross_rejects_same_line(self):
        with self.assertRaises(ValueError):
            self.engine._validate_ma_pair("ma5", "ma5")


class ScreenerSqlLogicTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from core import database

        self.database = database
        self.main_uri = "file:test_screener_main?mode=memory&cache=shared"
        self.ma_uri = "file:test_screener_ma?mode=memory&cache=shared"
        self.main_token = database.test_mem_var.set(self.main_uri)
        self.main_keepalive = database.connect_sqlite()
        self.ma_patch = patch.object(database, "_MA_MEM_DB_URI", self.ma_uri)
        self.ma_patch.start()
        self.ma_keepalive = database.connect_ma_db()

    def tearDown(self):
        self.ma_keepalive.close()
        self.ma_patch.stop()
        self.main_keepalive.close()
        self.database.test_mem_var.reset(self.main_token)

    async def test_disparity_uses_latest_common_timestamp(self):
        from services.screener_service import ScreenerEngine

        self.main_keepalive.execute(
            """
            CREATE TABLE minute_ohlcv (
                ticker TEXT NOT NULL, date INTEGER NOT NULL, time INTEGER NOT NULL,
                open INTEGER NOT NULL, high INTEGER NOT NULL, low INTEGER NOT NULL,
                close INTEGER NOT NULL, volume INTEGER NOT NULL, amount INTEGER,
                PRIMARY KEY (ticker, date, time)
            ) WITHOUT ROWID, STRICT
            """
        )
        self.main_keepalive.executemany(
            "INSERT INTO minute_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("TEST", 20260821, 100000, 100, 100, 100, 100, 1, 100),
                ("TEST", 20260821, 100100, 120, 120, 120, 120, 1, 120),
            ],
        )
        self.ma_keepalive.execute(
            """
            CREATE TABLE minute_ma (
                ticker TEXT NOT NULL, date INTEGER NOT NULL, time INTEGER NOT NULL,
                ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL, ma120 REAL, ma200 REAL,
                PRIMARY KEY (ticker, date, time)
            ) WITHOUT ROWID, STRICT
            """
        )
        self.ma_keepalive.execute(
            "INSERT INTO minute_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("TEST", 20260821, 100000, 100.0, None, None, None, None, None),
        )
        self.main_keepalive.commit()
        self.ma_keepalive.commit()

        result = await ScreenerEngine()._handle_disparity_value(
            "f1",
            {"line": "ma5", "threshold": 100, "direction": "above"},
            current_tickers={"TEST": {}},
        )

        self.assertEqual(result["TEST"]["f1"], 100.0)

    async def test_volume_breakout_excludes_current_candle_from_resistance(self):
        from services.screener_service import ScreenerEngine

        self.main_keepalive.execute(
            """
            CREATE TABLE daily_ohlcv (
                ticker TEXT NOT NULL, date INTEGER NOT NULL, open INTEGER NOT NULL,
                high INTEGER NOT NULL, low INTEGER NOT NULL, close INTEGER NOT NULL,
                volume INTEGER NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY (ticker, date)
            ) WITHOUT ROWID, STRICT
            """
        )
        self.main_keepalive.executemany(
            "INSERT INTO daily_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("TEST", 20260820, 90, 95, 85, 90, 100, 1000),
                ("TEST", 20260821, 96, 110, 95, 100, 1000, 2000),
                ("TEST", 20260822, 101, 120, 100, 115, 1000, 3000),
            ],
        )
        self.main_keepalive.commit()

        result = await ScreenerEngine()._handle_volume_peak_breakout(
            "f1", {"lookback": "1M"}, current_tickers={"TEST": {}}
        )

        self.assertEqual(result["TEST"]["f1"], round((115 - 110) / 110 * 100, 4))

    async def test_volume_tie_uses_most_recent_resistance(self):
        from services.screener_service import ScreenerEngine

        self.main_keepalive.execute(
            """
            CREATE TABLE daily_ohlcv (
                ticker TEXT NOT NULL, date INTEGER NOT NULL, open INTEGER NOT NULL,
                high INTEGER NOT NULL, low INTEGER NOT NULL, close INTEGER NOT NULL,
                volume INTEGER NOT NULL, amount INTEGER NOT NULL,
                PRIMARY KEY (ticker, date)
            ) WITHOUT ROWID, STRICT
            """
        )
        self.main_keepalive.executemany(
            "INSERT INTO daily_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("TEST", 20260820, 80, 90, 80, 85, 500, 1000),
                ("TEST", 20260821, 100, 110, 95, 100, 500, 2000),
                ("TEST", 20260822, 100, 105, 95, 100, 100, 3000),
            ],
        )
        self.main_keepalive.commit()

        result = await ScreenerEngine()._handle_volume_peak_breakout(
            "f1", {"lookback": "1M"}, current_tickers={"TEST": {}}
        )

        self.assertEqual(result, {})


class DailyMaIdempotencyTests(unittest.TestCase):
    def test_rebuild_daily_ma_is_idempotent_for_duplicate_ohlcv(self):
        import sqlite3

        from tasks.daily_ohlcv_scheduler import rebuild_daily_ma_for_ticker

        main_conn = sqlite3.connect(":memory:")
        ma_conn = sqlite3.connect(":memory:")
        try:
            main_conn.execute(
                "CREATE TABLE daily_ohlcv (ticker TEXT, date INTEGER, close INTEGER)"
            )
            main_conn.executemany(
                "INSERT INTO daily_ohlcv VALUES (?, ?, ?)",
                [("TEST", 20260820, 100), ("TEST", 20260821, 110)],
            )
            ma_conn.execute(
                """
                CREATE TABLE daily_ma (
                    ticker TEXT, date INTEGER, ma5 REAL, ma10 REAL, ma20 REAL,
                    ma60 REAL, ma120 REAL, ma200 REAL
                )
                """
            )

            rebuild_daily_ma_for_ticker(main_conn, ma_conn, "TEST")
            first = ma_conn.execute(
                "SELECT ticker, date, ma5 FROM daily_ma ORDER BY date"
            ).fetchall()
            rebuild_daily_ma_for_ticker(main_conn, ma_conn, "TEST")
            second = ma_conn.execute(
                "SELECT ticker, date, ma5 FROM daily_ma ORDER BY date"
            ).fetchall()

            self.assertEqual(second, first)
            self.assertEqual(len(second), 2)
        finally:
            main_conn.close()
            ma_conn.close()

    def test_rebuild_daily_ma_keeps_only_screener_horizon(self):
        import sqlite3

        from core.database import DAILY_MA_RETENTION
        from tasks.daily_ohlcv_scheduler import rebuild_daily_ma_for_ticker

        main_conn = sqlite3.connect(":memory:")
        ma_conn = sqlite3.connect(":memory:")
        try:
            main_conn.execute(
                "CREATE TABLE daily_ohlcv (ticker TEXT, date INTEGER, close INTEGER)"
            )
            main_conn.executemany(
                "INSERT INTO daily_ohlcv VALUES (?, ?, ?)",
                [("TEST", date, date) for date in range(1, 501)],
            )
            ma_conn.execute(
                """
                CREATE TABLE daily_ma (
                    ticker TEXT, date INTEGER, ma5 REAL, ma10 REAL, ma20 REAL,
                    ma60 REAL, ma120 REAL, ma200 REAL
                )
                """
            )

            rebuild_daily_ma_for_ticker(main_conn, ma_conn, "TEST")

            count, min_date, max_date = ma_conn.execute(
                "SELECT COUNT(*), MIN(date), MAX(date) FROM daily_ma"
            ).fetchone()
            self.assertEqual(count, DAILY_MA_RETENTION)
            self.assertEqual(min_date, 200)
            self.assertEqual(max_date, 500)
            ma200 = ma_conn.execute(
                "SELECT ma200 FROM daily_ma WHERE date = 200"
            ).fetchone()[0]
            self.assertEqual(ma200, 100.5)
        finally:
            main_conn.close()
            ma_conn.close()
