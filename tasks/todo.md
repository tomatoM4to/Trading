# Task List

## Phase 1: Overlap-Aware Core Logic
- [x] Task 1: Update `process_ticker` in `app/tasks/minute_ohlcv_scheduler.py`
  - Restore `max_steps=15` as the default.
  - Fix the midnight bug: if `df.empty`, decrement `target_date` by 1 day, set `target_time="153000"`, and `continue` instead of `break`.
  - Implement Early Exit: if `df["dt_str"].min() <= last_datetime`, filter the dataframe to `> last_datetime`, save, and `break`.

## Phase 2: Refactoring and Clean Up
- [x] Task 2: Remove `run_minute_backfill_task` from `app/tasks/minute_ohlcv_scheduler.py`.
- [x] Task 3: Update `app/core/bootstrap.py` to remove the background task creation for backfilling and ensure the main scheduler is started without waiting for 08:55.
