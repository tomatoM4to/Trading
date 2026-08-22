import argparse
import csv
import json
import time
from datetime import datetime
from typing import Any

import requests


class BenchmarkStreamError(RuntimeError):
    """Raised when the screener SSE stream does not complete successfully."""


def read_screener_stream(lines) -> int:
    """Return the completed item count or raise for an SSE-level failure."""
    for line in lines:
        if not line:
            continue
        decoded = line.decode("utf-8")
        if not decoded.startswith("data: "):
            continue
        try:
            data = json.loads(decoded[6:])
        except json.JSONDecodeError:
            continue
        if data.get("type") == "error":
            raise BenchmarkStreamError(data.get("message") or "Unknown screener error")
        if data.get("type") == "complete":
            return len(data.get("items", []))
    raise BenchmarkStreamError("SSE stream ended without a complete event")


def filter_node(filter_id: str, filter_type: str, **params: Any) -> dict[str, Any]:
    return {"id": filter_id, "type": filter_type, "params": params}


def scenario(
    name: str, filters: list[dict[str, Any]], operations: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "payload": {"filters": filters, "operations": operations or []},
    }


SCENARIOS = [
    scenario(
        "Light 1 (Daily Alignment, 5 Sessions)",
        [
            filter_node(
                "l1",
                "ma_alignment",
                lines=["ma_daily_5", "ma_daily_20", "ma_daily_60"],
                duration=5,
            )
        ],
    ),
    scenario(
        "Light 2 (Daily Golden Cross, 20 Sessions)",
        [
            filter_node(
                "l2",
                "ma_cross",
                short_line="ma_daily_5",
                long_line="ma_daily_20",
                direction="golden",
                within=20,
            )
        ],
    ),
    scenario(
        "Light 3 (Minute Golden Cross, 60 Minutes)",
        [
            filter_node(
                "l3",
                "ma_cross",
                short_line="ma5",
                long_line="ma20",
                direction="golden",
                within=60,
            )
        ],
    ),
    scenario(
        "Light 4 (Daily Convergence, 10 Sessions)",
        [
            filter_node(
                "l4",
                "ma_convergence_consolidation",
                lines=["ma_daily_5", "ma_daily_20", "ma_daily_60"],
                threshold=3.0,
                duration=10,
            )
        ],
    ),
    scenario(
        "Light 5 (Daily MA20 Disparity Above 105)",
        [
            filter_node(
                "l5",
                "disparity_value",
                line="ma_daily_20",
                threshold=105.0,
                direction="above",
            )
        ],
    ),
    scenario(
        "Light 6 (Daily 1M Volume Peak Breakout)",
        [filter_node("l6", "volume_peak_breakout", lookback="1M")],
    ),
    scenario(
        "Light 7 (Three-Way Daily Opportunity OR)",
        [
            filter_node(
                "l7a",
                "ma_cross",
                short_line="ma_daily_5",
                long_line="ma_daily_20",
                direction="golden",
                within=20,
            ),
            filter_node(
                "l7b",
                "ma_convergence_point",
                lines=["ma_daily_5", "ma_daily_20", "ma_daily_60"],
                threshold=2.0,
                within=20,
            ),
            filter_node("l7c", "volume_peak_breakout", lookback="3M"),
        ],
        ["OR", "OR"],
    ),
    scenario(
        "Heavy 1 (Daily 300-Candle Alignment Scan)",
        [
            filter_node(
                "h1",
                "ma_alignment",
                lines=[
                    "ma_daily_5",
                    "ma_daily_10",
                    "ma_daily_20",
                    "ma_daily_60",
                    "ma_daily_120",
                    "ma_daily_200",
                ],
                duration=300,
            )
        ],
    ),
    scenario(
        "Heavy 2 (Minute 390-Candle Alignment Scan)",
        [
            filter_node(
                "h2",
                "ma_alignment",
                lines=["ma5", "ma10", "ma20", "ma60", "ma120", "ma200"],
                duration=390,
            )
        ],
    ),
    scenario(
        "Heavy 3 (Minute 390-Candle Convergence Scan)",
        [
            filter_node(
                "h3",
                "ma_convergence_consolidation",
                lines=["ma5", "ma10", "ma20", "ma60", "ma120", "ma200"],
                threshold=5.0,
                duration=390,
            )
        ],
    ),
    scenario(
        "Heavy 4 (Three-Way Full-Scan OR)",
        [
            filter_node(
                "h4a",
                "ma_alignment",
                lines=["ma5", "ma10", "ma20", "ma60", "ma120", "ma200"],
                duration=300,
            ),
            filter_node(
                "h4b",
                "ma_convergence_consolidation",
                lines=["ma5", "ma20", "ma60", "ma120", "ma200"],
                threshold=5.0,
                duration=300,
            ),
            filter_node(
                "h4c",
                "ma_cross",
                short_line="ma5",
                long_line="ma200",
                direction="golden",
                within=390,
            ),
        ],
        ["OR", "OR"],
    ),
    scenario(
        "Heavy 5 (Two-Way Multi-Timeframe OR)",
        [
            filter_node(
                "h5a",
                "ma_convergence_consolidation",
                lines=[
                    "ma_daily_5",
                    "ma_daily_10",
                    "ma_daily_20",
                    "ma_daily_60",
                    "ma_daily_120",
                    "ma_daily_200",
                ],
                threshold=5.0,
                duration=300,
            ),
            filter_node(
                "h5b",
                "ma_cross",
                short_line="ma5",
                long_line="ma200",
                direction="golden",
                within=390,
            ),
        ],
        ["OR"],
    ),
]


def run_benchmark(host: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"screener_benchmark_{timestamp}.csv"

    print(f"Starting Screener Benchmark against {host}")
    print(f"Results will be saved to {csv_filename}\n")

    results = []

    for index, current_scenario in enumerate(SCENARIOS, 1):
        name = current_scenario["name"]
        payload = current_scenario["payload"]

        print(f"[{index}/{len(SCENARIOS)}] Running: {name} ... ", end="", flush=True)

        start_time = time.perf_counter()
        tickers_found = 0
        status = "Success"

        try:
            with requests.post(
                f"{host}/api/screener/run", json=payload, stream=True, timeout=120
            ) as response:
                response.raise_for_status()
                tickers_found = read_screener_stream(response.iter_lines())
        except requests.exceptions.RequestException as exc:
            status = f"Error: {exc}"
        except Exception as exc:
            status = f"Error: {exc}"

        duration = time.perf_counter() - start_time

        if status == "Success":
            print(f"Done in {duration:.2f}s ({tickers_found} tickers found)")
        else:
            print(f"FAILED in {duration:.2f}s ({status})")

        results.append(
            {
                "Scenario Name": name,
                "Duration (s)": round(duration, 3),
                "Tickers Found": tickers_found,
                "Status": status,
            }
        )

    print(f"\nWriting results to {csv_filename} ...")
    with open(csv_filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["Scenario Name", "Duration (s)", "Tickers Found", "Status"],
        )
        writer.writeheader()
        writer.writerows(results)

    print("Benchmark completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Screener Benchmark")
    parser.add_argument(
        "--host",
        type=str,
        default="https://168.107.28.167.nip.io",
        help="Target server host",
    )
    args = parser.parse_args()

    run_benchmark(args.host)
