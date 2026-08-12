# Implementation Plan: Data Retention & 200MA Stabilization

## 1. Components & Dependencies
- `app/core/scheduler.py`: Contains the `cleanup_ohlcv_job` which executes the GC queries.
- `app/tasks/minute_ohlcv_scheduler.py`: Contains the `process_ticker` logic for cold-start minute data fetching, bounded by `max_steps`.

## 2. Implementation Order
1. **Update Minute Scheduler**: Change `max_steps` from 15 to 7 in `minute_ohlcv_scheduler.py`.
2. **Update GC Logic**: Change the GC deletion thresholds in `scheduler.py` from `-7 days` to `-2 days` (minute) and `-300 days` to `-500 days` (daily).

## 3. Risks & Mitigations
- **Risk**: 2-day minute data might be too short if the weekend intervenes.
- **Mitigation**: The `-2 days` in SQLite means 48 hours. However, since the GC runs daily at 23:00, Friday's data will be deleted on Sunday 23:00. This is okay since weekends have no trading, and on Monday we only care about Monday's data for day-trading.
- **Risk**: Database size grows rapidly due to 500-day retention for daily data.
- **Mitigation**: Daily data is extremely compact compared to minute data. 500 days of data across 2,400 stocks is ~1.2 million rows, easily manageable in SQLite.

## 4. Verification Checkpoints
- Run `uv run ruff check .` to ensure no syntax errors.
- Ensure the logic changes align exactly with the Phase 1 Spec.
