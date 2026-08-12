# Implementation Plan: Intelligent GC

## 1. Components & Dependencies
- `app/core/scheduler.py`: Contains the `cleanup_ohlcv_job` and the scheduler registration logic.
- `datetime`: Needs to be imported in `app/core/scheduler.py` to calculate `yesterday`.

## 2. Implementation Order
1. **Update Scheduler Timing**: Change the cron trigger for `cleanup_ohlcv_job` from `hour=23` to `hour=4` in `start()` method.
2. **Import Datetime**: Add `from datetime import datetime, timedelta` to `app/core/scheduler.py`.
3. **Implement Smart Trigger**: Inside `cleanup_ohlcv_job`, check if yesterday's data exists in `daily_ohlcv`. If not, return early.
4. **Implement Intelligent Deletion**: Replace the existing date string comparisons with the Temporary Table and Window Function logic.

## 3. Risks & Mitigations
- **Risk**: SQLite temporary tables might conflict if not cleaned up.
- **Mitigation**: Use `IF NOT EXISTS` for creation, `DELETE FROM` to clear before insert, and SQLite will drop them when the connection is closed.
- **Risk**: Python's `datetime.now()` might be in UTC if not careful.
- **Mitigation**: The APScheduler already enforces `Asia/Seoul`, but we can be explicit, or just rely on local time if the container timezone is KST. We'll use standard `datetime.now()` as the server is expected to be in KST, or better yet, we can use KST directly but for simplicity `datetime.now()` is standard in this project. (Actually, `datetime.now()` is fine if the OS is in KST).

## 4. Verification Checkpoints
- Run `uv run ruff check .` to ensure no syntax or import errors.
- Ensure the SQL queries are syntactically valid SQLite queries.
