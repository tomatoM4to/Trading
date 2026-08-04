# Plan: Screener Performance Benchmark

## 1. Components
- **Benchmark Script**: A standalone python script (`scripts/benchmark_screener.py`) that stores the 10 predefined payloads and orchestrates the serial requests.
- **SSE Parser**: A function to send POST requests and parse the `text/event-stream` format to detect the `complete` event.
- **CSV Logger**: A function to format the results and write them to a timestamped file (`screener_benchmark_YYYYMMDD_HHMMSS.csv`).

## 2. Implementation Order
1. Define the 10 payloads (Light 1-5, Heavy 1-5) matching `schemas/screener.py`.
2. Implement the HTTP runner and SSE parser.
3. Wire up the CSV logging with the dynamic timestamp.
4. Add CLI arguments (e.g., `--host`) for flexibility.

## 3. Risks & Mitigations
- **Network timeout**: Set a reasonable timeout (e.g., 60s) for the `requests.post` call, especially for Heavy scenarios.
- **Backend errors**: Wrap the execution in a try-except block so one failed scenario doesn't crash the entire benchmark suite.
