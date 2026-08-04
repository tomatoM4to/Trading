import argparse
import csv
import json
import time
from datetime import datetime
import requests

SCENARIOS = [
    {
        "name": "Light 1 (Daily Cross)",
        "payload": {
            "filters": [
                {
                    "id": "f1",
                    "type": "ma_cross",
                    "params": {"short_line": "ma_daily_5", "long_line": "ma_daily_20", "direction": "golden", "within": 1}
                }
            ],
            "operations": []
        }
    },
    {
        "name": "Light 2 (Minute Cross)",
        "payload": {
            "filters": [
                {
                    "id": "f2",
                    "type": "ma_cross",
                    "params": {"short_line": "ma5", "long_line": "ma20", "direction": "golden", "within": 1}
                }
            ],
            "operations": []
        }
    },
    {
        "name": "Light 3 (Daily Alignment)",
        "payload": {
            "filters": [
                {
                    "id": "f3",
                    "type": "ma_alignment",
                    "params": {"lines": ["ma_daily_5", "ma_daily_20", "ma_daily_60"], "duration": 2}
                }
            ],
            "operations": []
        }
    },
    {
        "name": "Light 4 (Minute Convergence Point)",
        "payload": {
            "filters": [
                {
                    "id": "f4",
                    "type": "ma_convergence_point",
                    "params": {"lines": ["ma5", "ma20"], "threshold": 3.0, "within": 1}
                }
            ],
            "operations": []
        }
    },
    {
        "name": "Light 5 (Daily Alignment + Foreign Buy Rank)",
        "payload": {
            "filters": [
                {
                    "id": "f5a",
                    "type": "ma_alignment",
                    "params": {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 1}
                },
                {
                    "id": "f5b",
                    "type": "foreign_net_buy_rank",
                    "params": {"limit": 30}
                }
            ],
            "operations": ["AND"]
        }
    },
    {
        "name": "Heavy 1 (Daily Deep Window)",
        "payload": {
            "filters": [
                {"id": "h1a", "type": "ma_alignment", "params": {"lines": ["ma_daily_5", "ma_daily_10", "ma_daily_20", "ma_daily_60", "ma_daily_120"], "duration": 5}},
                {"id": "h1b", "type": "ma_convergence_consolidation", "params": {"lines": ["ma_daily_20", "ma_daily_60"], "threshold": 2.0, "duration": 5}},
                {"id": "h1c", "type": "ma_cross", "params": {"short_line": "ma_daily_5", "long_line": "ma_daily_20", "direction": "golden", "within": 3}},
                {"id": "h1d", "type": "foreign_net_buy_rank", "params": {"limit": 50}},
                {"id": "h1e", "type": "inst_net_buy_rank", "params": {"limit": 50}}
            ],
            "operations": ["AND", "AND", "AND", "AND"]
        }
    },
    {
        "name": "Heavy 2 (Minute Stress Test)",
        "payload": {
            "filters": [
                {"id": "h2a", "type": "ma_alignment", "params": {"lines": ["ma5", "ma10", "ma20", "ma60", "ma120"], "duration": 10}},
                {"id": "h2b", "type": "ma_convergence_consolidation", "params": {"lines": ["ma20", "ma60"], "threshold": 1.5, "duration": 10}},
                {"id": "h2c", "type": "ma_cross", "params": {"short_line": "ma5", "long_line": "ma20", "direction": "golden", "within": 5}},
                {"id": "h2d", "type": "foreign_net_buy_rank", "params": {"limit": 30}},
                {"id": "h2e", "type": "inst_net_buy_rank", "params": {"limit": 30}}
            ],
            "operations": ["AND", "AND", "AND", "AND"]
        }
    },
    {
        "name": "Heavy 3 (Mixed Timeframes Combo)",
        "payload": {
            "filters": [
                {"id": "h3a", "type": "ma_alignment", "params": {"lines": ["ma_daily_20", "ma_daily_60", "ma_daily_120"], "duration": 5}},
                {"id": "h3b", "type": "ma_alignment", "params": {"lines": ["ma5", "ma10", "ma20"], "duration": 5}},
                {"id": "h3c", "type": "ma_convergence_point", "params": {"lines": ["ma20", "ma60"], "threshold": 1.0, "within": 3}},
                {"id": "h3d", "type": "ma_cross", "params": {"short_line": "ma5", "long_line": "ma20", "direction": "golden", "within": 1}},
                {"id": "h3e", "type": "foreign_net_buy_rank", "params": {"limit": 60}}
            ],
            "operations": ["AND", "AND", "AND", "AND"]
        }
    },
    {
        "name": "Heavy 4 (Extreme Window Functions)",
        "payload": {
            "filters": [
                {"id": "h4a", "type": "ma_alignment", "params": {"lines": ["ma_daily_5", "ma_daily_10", "ma_daily_20", "ma_daily_60", "ma_daily_120"], "duration": 15}},
                {"id": "h4b", "type": "ma_convergence_consolidation", "params": {"lines": ["ma_daily_5", "ma_daily_10", "ma_daily_20"], "threshold": 5.0, "duration": 15}},
                {"id": "h4c", "type": "ma_cross", "params": {"short_line": "ma_daily_5", "long_line": "ma_daily_60", "direction": "golden", "within": 10}},
                {"id": "h4d", "type": "ma_cross", "params": {"short_line": "ma5", "long_line": "ma60", "direction": "golden", "within": 10}},
                {"id": "h4e", "type": "foreign_net_buy_rank", "params": {"limit": 30}}
            ],
            "operations": ["AND", "AND", "AND", "AND"]
        }
    },
    {
        "name": "Heavy 5 (Full Minute DB Scan)",
        "payload": {
            "filters": [
                {"id": "h5a", "type": "ma_alignment", "params": {"lines": ["ma10", "ma20", "ma60", "ma120"], "duration": 15}},
                {"id": "h5b", "type": "ma_convergence_consolidation", "params": {"lines": ["ma5", "ma10", "ma20", "ma60", "ma120"], "threshold": 3.0, "duration": 10}},
                {"id": "h5c", "type": "ma_cross", "params": {"short_line": "ma5", "long_line": "ma120", "direction": "golden", "within": 10}},
                {"id": "h5d", "type": "foreign_net_buy_rank", "params": {"limit": 30}},
                {"id": "h5e", "type": "inst_net_buy_rank", "params": {"limit": 30}}
            ],
            "operations": ["AND", "AND", "AND", "AND"]
        }
    }
]


def run_benchmark(host: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"screener_benchmark_{timestamp}.csv"

    print(f"Starting Screener Benchmark against {host}")
    print(f"Results will be saved to {csv_filename}\n")

    results = []

    for i, scenario in enumerate(SCENARIOS, 1):
        name = scenario["name"]
        payload = scenario["payload"]

        print(f"[{i}/{len(SCENARIOS)}] Running: {name} ... ", end="", flush=True)

        start_time = time.perf_counter()

        tickers_found = 0
        status = "Success"

        try:
            with requests.post(f"{host}/api/screener/run", json=payload, stream=True, timeout=120) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith("data: "):
                            try:
                                data = json.loads(decoded[6:])
                                if data.get("type") == "complete":
                                    items = data.get("items", [])
                                    tickers_found = len(items)
                                    break
                            except json.JSONDecodeError:
                                pass
        except requests.exceptions.RequestException as e:
            status = f"Error: {e}"
        except Exception as e:
            status = f"Error: {e}"

        duration = time.perf_counter() - start_time

        if status == "Success":
            print(f"Done in {duration:.2f}s ({tickers_found} tickers found)")
        else:
            print(f"FAILED in {duration:.2f}s ({status})")

        results.append({
            "Scenario Name": name,
            "Duration (s)": round(duration, 3),
            "Tickers Found": tickers_found,
            "Status": status
        })

    print(f"\nWriting results to {csv_filename} ...")
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Scenario Name", "Duration (s)", "Tickers Found", "Status"])
        writer.writeheader()
        writer.writerows(results)

    print("Benchmark completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Screener Benchmark")
    parser.add_argument("--host", type=str, default="https://168.107.55.31.nip.io", help="Target server host")
    args = parser.parse_args()

    run_benchmark(args.host)
