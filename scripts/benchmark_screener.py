import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def benchmark(tickers, repeats):
    from tempfile import TemporaryDirectory

    from tests.support import OfflineEnvironment, Sandbox

    with (
        TemporaryDirectory(prefix="trading-harness-") as root,
        OfflineEnvironment(root) as offline,
        Sandbox(offline) as box,
    ):
        return await measure(box, tickers, repeats)


async def measure(box, tickers, repeats):
    from core import database
    from core.bootstrap import rebuild_ma_database
    from schemas.screener import ScreenerRequest
    from services.screener_service import ScreenerEngine

    from tests.data import daily_series, ma_reference, minute_series
    from tests.metrics import peak_rss

    start = time.perf_counter()
    processed = 0
    expected = {}
    for i in range(tickers):
        ticker = f"{i:06}"
        box.stock(ticker)
        for minute in (False, True):
            rows = minute_series(590, ticker) if minute else daily_series(500, ticker)
            ordered = []
            for index, row in enumerate(rows):
                close = 100 + index if i % 2 == 0 else 1000 - index
                ordered.append(
                    (
                        *row[: 3 if minute else 2],
                        close,
                        close + 3,
                        close - 3,
                        close,
                        row[-2],
                        close * row[-2],
                    )
                )
            table, slots = (
                ("minute_ohlcv", "?,?,?,?,?,?,?,?,?")
                if minute
                else ("daily_ohlcv", "?,?,?,?,?,?,?,?")
            )
            columns = (
                "ticker,date,time,open,high,low,close,volume,amount"
                if minute
                else "ticker,date,open,high,low,close,volume,amount"
            )
            box.write(f"INSERT INTO {table} ({columns}) VALUES ({slots})", ordered)
            processed += len(ordered)
            if minute and i % 2 == 0:
                values = ma_reference(ordered, minute=True)[-1]
                expected[ticker] = {
                    "alignment": round((values[3] - values[5]) / values[5] * 100, 4)
                }
    await rebuild_ma_database()
    hydration_seconds = time.perf_counter() - start
    engine = ScreenerEngine()
    request = ScreenerRequest(
        filters=[
            {
                "id": "alignment",
                "type": "ma_alignment",
                "params": {"lines": ["ma5", "ma20"], "duration": 1},
            }
        ],
        operations=[],
    )
    runs = []
    for _ in range(repeats):
        started = time.perf_counter()
        events = [
            json.loads(event.removeprefix("data: "))
            async for event in engine.run_pipeline_stream(request)
        ]
        elapsed = time.perf_counter() - started
        terminals = [e for e in events if e["type"] in {"error", "complete"}]
        if len(terminals) != 1 or terminals[0]["type"] != "complete":
            raise AssertionError("Benchmark stream did not complete successfully")
        actual = {
            item["ticker"]: item["filter_values"] for item in terminals[0]["items"]
        }
        if not expected or actual != expected:
            raise AssertionError(
                "Benchmark result differs from independently calculated nonempty reference"
            )
        runs.append(
            {
                "seconds": round(elapsed, 6),
                "matched": len(actual),
                "success": 1,
                "failure": 0,
            }
        )
    conn = database.connect_ma_db()
    try:
        retained = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("daily_ma", "minute_ma")
        }
    finally:
        conn.close()
    return {
        "mode": "offline-synthetic",
        "tickers": tickers,
        "processed_records": processed,
        "retained_ma": retained,
        "hydration_seconds": round(hydration_seconds, 6),
        "peak_rss_bytes": peak_rss(),
        "rss_scope": "Python benchmark process; excludes OS page cache",
        "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Offline correctness-gated screener benchmark; never contacts a server"
    )
    parser.add_argument("--tickers", type=int, default=64)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if not 2 <= args.tickers <= 2400 or not 1 <= args.repeats <= 20:
        parser.error("tickers must be 2..2400 and repeats 1..20")
    result = asyncio.run(benchmark(args.tickers, args.repeats))
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
