import asyncio
import logging
import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


class SecurityRegressionTests(unittest.TestCase):
    def test_kis_request_log_redacts_credentials(self):
        from core.kis_fetch import redact_headers

        headers = {
            "authorization": "Bearer secret-token",
            "appkey": "secret-app-key",
            "appsecret": "secret-app-secret",
            "tr_id": "TEST_TR",
        }

        redacted = redact_headers(headers)

        self.assertEqual(redacted["authorization"], "***")
        self.assertEqual(redacted["appkey"], "***")
        self.assertEqual(redacted["appsecret"], "***")
        self.assertEqual(redacted["tr_id"], "TEST_TR")

    def test_admin_api_key_fails_closed_when_not_configured(self):
        from core.dependencies import verify_admin_api_key
        from fastapi import HTTPException

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                verify_admin_api_key(None)

        self.assertEqual(raised.exception.status_code, 503)

    def test_admin_api_key_rejects_invalid_key(self):
        from core.dependencies import verify_admin_api_key
        from fastapi import HTTPException

        with patch.dict(os.environ, {"ADMIN_API_KEY": "expected"}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                verify_admin_api_key("wrong")

        self.assertEqual(raised.exception.status_code, 401)

    def test_admin_api_key_accepts_valid_key(self):
        from core.dependencies import verify_admin_api_key

        with patch.dict(os.environ, {"ADMIN_API_KEY": "expected"}, clear=True):
            verify_admin_api_key("expected")

    def test_admin_router_requires_api_key(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routes.admin import router

        app = FastAPI()
        app.include_router(router)

        with patch.dict(os.environ, {"ADMIN_API_KEY": "expected"}, clear=True):
            response = TestClient(app).get("/admin/live/global-status?data_type=daily")

        self.assertEqual(response.status_code, 401)


class ScreenerRegressionTests(unittest.TestCase):
    def setUp(self):
        from services.screener_service import ScreenerEngine

        self.engine = ScreenerEngine()

    def test_threshold_rejects_sql_expression(self):
        with self.assertRaises(ValueError):
            self.engine._validate_threshold("0 OR 1=1")

    def test_threshold_rejects_non_finite_number(self):
        with self.assertRaises(ValueError):
            self.engine._validate_threshold(float("inf"))

    def test_threshold_accepts_finite_non_negative_number(self):
        self.assertEqual(self.engine._validate_threshold("2.5"), 2.5)

    def test_rank_limit_must_be_between_one_and_thirty(self):
        for invalid in (0, 31, -1, "30", True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.engine._validate_rank_limit(invalid)

    def test_daily_disparity_uses_daily_tables(self):
        self.assertTrue(self.engine._is_daily_line("ma_daily_5"))
        self.assertFalse(self.engine._is_daily_line("ma5"))


class DatabaseRegressionTests(unittest.TestCase):
    def test_sync_failure_is_propagated(self):
        from core.database import sync_memory_to_disk

        source = sqlite3.connect(":memory:")
        try:
            with patch(
                "core.database.sqlite3.connect", side_effect=sqlite3.Error("fail")
            ):
                with self.assertRaises(sqlite3.Error):
                    sync_memory_to_disk(mem_conn=source)
        finally:
            source.close()


class KisQueueLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        from core import kis_fetch

        await kis_fetch.stop_q_worker()

    async def test_worker_can_restart_after_stop(self):
        from core import kis_fetch

        await kis_fetch.start_q_worker()
        first_worker = kis_fetch._kis_worker_task
        await kis_fetch.stop_q_worker()
        await kis_fetch.start_q_worker()

        self.assertIsNotNone(kis_fetch._kis_worker_task)
        self.assertIsNot(kis_fetch._kis_worker_task, first_worker)
        self.assertFalse(kis_fetch._kis_worker_task.done())


class ScreenerQueryRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_convergence_threshold_is_bound_and_query_executes(self):
        from core import database
        from services.screener_service import ScreenerEngine

        test_ma_uri = "file:test_regression_ma?mode=memory&cache=shared"
        with patch.object(database, "_MA_MEM_DB_URI", test_ma_uri):
            conn = database.connect_ma_db()
            try:
                conn.execute(
                    """
                    CREATE TABLE daily_ma (
                        ticker TEXT NOT NULL,
                        date INTEGER NOT NULL,
                        ma5 REAL,
                        ma10 REAL,
                        ma20 REAL,
                        ma60 REAL,
                        ma120 REAL,
                        ma200 REAL,
                        PRIMARY KEY (ticker, date)
                    ) WITHOUT ROWID, STRICT
                    """
                )
                conn.execute(
                    "INSERT INTO daily_ma (ticker, date, ma5, ma20) VALUES (?, ?, ?, ?)",
                    ("TEST", 20260821, 100.0, 101.0),
                )
                conn.commit()
                result = await ScreenerEngine()._handle_ma_convergence_point(
                    "filter-1",
                    {
                        "lines": ["ma_daily_5", "ma_daily_20"],
                        "threshold": 2.0,
                        "within": 1,
                    },
                    current_tickers={"TEST": {}},
                )
            finally:
                conn.close()

        self.assertIn("TEST", result)


class BackgroundTaskLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_background_tasks_waits_for_cancellation(self):
        from main import cancel_background_tasks

        cancelled = asyncio.Event()

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(worker())
        await asyncio.sleep(0)
        await cancel_background_tasks([task])

        self.assertTrue(task.cancelled())
        self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
