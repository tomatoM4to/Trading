import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

from tests import support
from tests.transport import FakeTransport, response


async def main():
    root = Path(sys.argv[1]).resolve()
    if not root.is_relative_to(
        Path(__import__("tempfile").gettempdir()).resolve()
    ) or not any(p.startswith("trading-harness-") for p in root.parts):
        raise ValueError("Crash probe requires a harness temporary directory")
    support.SESSION_PATH = root
    from core import database

    from tasks import daily_ohlcv_scheduler as daily

    database.test_db_var.set(str(root / "canonical.db"))
    ma_uri = "file:crash_worker_ma?mode=memory&cache=shared"
    support.ALLOWED_MEMORY.add(ma_uri)
    database._MA_MEM_DB_URI = ma_uri
    database.init_sqlite_connection()
    if sys.argv[2] == "mid-transaction":
        conn = database.connect_sqlite()
        conn.execute(
            "CREATE TRIGGER crash_write BEFORE INSERT ON daily_ohlcv WHEN NEW.date=20261111 BEGIN SELECT crash_now(); END"
        )
        conn.commit()
        conn.close()
        original = database.connect_sqlite

        def connection():
            result = original()
            result.create_function("crash_now", 0, lambda: os._exit(23))
            return result

        with (
            patch.object(database, "connect_sqlite", connection),
            FakeTransport([response(support.fixture("candles.json")["daily"])]),
        ):
            await daily.process_ticker("A", target_api_calls=1)
    else:
        with (
            patch.object(
                daily,
                "rebuild_daily_ma_for_ticker",
                side_effect=lambda *args: os._exit(23),
            ),
            FakeTransport([response(support.fixture("candles.json")["daily"])]),
        ):
            await daily.process_ticker("A", target_api_calls=1)
    raise AssertionError("Crash injection was not reached")


if __name__ == "__main__":
    asyncio.run(main())
