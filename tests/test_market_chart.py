import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


class MarketChartRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_chart_returns_ten_day_moving_average(self):
        from services.market_service import get_chart_data

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE stock_codes (ticker TEXT PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO stock_codes VALUES (?, ?)", ("TEST", "테스트"))
        conn.execute(
            """
            CREATE TABLE daily_ohlcv (
                ticker TEXT NOT NULL,
                date INTEGER NOT NULL,
                open INTEGER NOT NULL,
                high INTEGER NOT NULL,
                low INTEGER NOT NULL,
                close INTEGER NOT NULL,
                volume INTEGER NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO daily_ohlcv VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("TEST", 20260800 + day, day, day, day, day, 100) for day in range(1, 11)],
        )
        conn.commit()

        try:
            with patch("services.market_service.connect_sqlite", return_value=conn):
                response = await get_chart_data("TEST", timeframe="daily")

            self.assertIsNone(response.data[8].ma_daily_10)
            self.assertEqual(response.data[9].ma_daily_10, 5.5)
        finally:
            conn.close()
