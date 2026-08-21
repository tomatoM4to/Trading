import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


class DiskCanonicalDatabaseTests(unittest.TestCase):
    def test_initialization_keeps_ohlcv_on_disk(self):
        from core import database

        with tempfile.TemporaryDirectory() as temp_dir:
            disk_path = Path(temp_dir) / "trading.db"
            ma_uri = "file:test_disk_canonical_ma?mode=memory&cache=shared"
            old_keepalive = database._keepalive_ma_conn
            try:
                with (
                    patch.dict(os.environ, {"SQLITE_DB_PATH": str(disk_path)}),
                    patch.object(database, "_MA_MEM_DB_URI", ma_uri),
                ):
                    database.init_sqlite_connection()

                    self.assertEqual(database.get_sqlite_db_path(), disk_path.resolve())
                    conn = database.connect_sqlite()
                    try:
                        database_paths = {
                            row[2] for row in conn.execute("PRAGMA database_list")
                        }
                        self.assertIn(str(disk_path.resolve()), database_paths)
                    finally:
                        conn.close()
            finally:
                if database._keepalive_ma_conn is not old_keepalive:
                    database._keepalive_ma_conn.close()
                    database._keepalive_ma_conn = old_keepalive


class MaRetentionTests(unittest.TestCase):
    def test_prune_ma_history_keeps_latest_rows_per_ticker(self):
        from core.database import prune_ma_history

        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                "CREATE TABLE daily_ma (ticker TEXT, date INTEGER, PRIMARY KEY (ticker, date))"
            )
            conn.executemany(
                "INSERT INTO daily_ma VALUES (?, ?)",
                [(ticker, date) for ticker in ("A", "B") for date in range(1, 6)],
            )

            prune_ma_history(conn, "daily_ma", limit=3)

            rows = conn.execute(
                "SELECT ticker, date FROM daily_ma ORDER BY ticker, date"
            ).fetchall()
            self.assertEqual(
                rows,
                [("A", 3), ("A", 4), ("A", 5), ("B", 3), ("B", 4), ("B", 5)],
            )
        finally:
            conn.close()
