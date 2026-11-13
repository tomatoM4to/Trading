import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def benchmark(tickers):
    from tests.support import OfflineEnvironment, Sandbox

    with (
        TemporaryDirectory(prefix="trading-harness-") as root,
        OfflineEnvironment(root) as offline,
        Sandbox(offline) as box,
    ):
        from core import kis_fetch
        from tasks.daily_ohlcv_scheduler import process_ticker

        from tests.data import daily_series, daily_wire, ma_reference
        from tests.metrics import peak_rss
        from tests.transport import FakeTransport, response

        source = {f"{i:06d}": daily_series(501, f"{i:06d}") for i in range(tickers)}
        active = {ticker: rows[:-1] for ticker, rows in source.items()}
        submitted = []
        original_fetch = kis_fetch.async_kis_fetch

        async def observed_fetch(*args, **kwargs):
            submitted.append(time.perf_counter())
            return await original_fetch(*args, **kwargs)

        def reply(call):
            params = call.params
            rows = [
                row
                for row in active[params["FID_INPUT_ISCD"]]
                if int(params["FID_INPUT_DATE_1"])
                <= row[1]
                <= int(params["FID_INPUT_DATE_2"])
            ]
            return response(daily_wire(rows[-100:][::-1]))

        def verify(expected):
            assert box.rows("daily_ohlcv") == sorted(
                row for rows in expected.values() for row in rows
            )
            assert box.rows("daily_ma") == sorted(
                row
                for rows in expected.values()
                for row in ma_reference(rows, retention=301)
            )

        measurements = []
        try:
            with patch("tasks.daily_ohlcv_scheduler.async_kis_fetch", observed_fetch):
                for mode in ("cold", "increment", "gap"):
                    if mode == "increment":
                        active = source
                    if mode == "gap":
                        box.write(
                            "DELETE FROM daily_ohlcv WHERE ticker=? AND date=?",
                            [(ticker, rows[40][1]) for ticker, rows in source.items()],
                        )
                    submitted.clear()
                    with FakeTransport([reply] * (tickers * 5)) as transport:
                        started = time.perf_counter()
                        await asyncio.gather(
                            *(
                                process_ticker(
                                    ticker,
                                    last_date=None if mode == "cold" else rows[-1][1],
                                )
                                for ticker, rows in active.items()
                            )
                        )
                        elapsed = time.perf_counter() - started
                    verify(active)
                    assert len(submitted) == len(transport.calls)
                    measurements.append(
                        {
                            "mode": mode,
                            "calls": len(transport.calls),
                            "seconds": round(elapsed, 6),
                            "queue_wait_seconds": round(
                                sum(
                                    call.start - at
                                    for call, at in zip(
                                        transport.calls, submitted, strict=True
                                    )
                                ),
                                6,
                            ),
                            "ohlcv_rows": sum(map(len, active.values())),
                            "correct": True,
                        }
                    )
        finally:
            await kis_fetch.stop_q_worker()
        return {
            "mode": "offline-synthetic",
            "tickers": tickers,
            "measurements": measurements,
            "peak_rss_bytes": peak_rss(),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synthetic daily collection; real Queue and independent full OHLCV/MA comparison"
    )
    parser.add_argument("--tickers", type=int, choices=range(1, 101), default=4)
    print(json.dumps(asyncio.run(benchmark(parser.parse_args().tickers)), indent=2))
