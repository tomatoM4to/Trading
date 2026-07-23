# Implementation Plan: Unified Minute OHLCV Scheduler

## Overview
We will refactor the minute OHLCV scheduler back to a simple, unified architecture. The decoupled `backfill` task will be removed. The single `process_ticker` function will handle both cold-start historical backfilling (up to 3 days) and shallow real-time polling (1 minute) by dynamically breaking its API loop when it detects that the fetched data overlaps with existing database records. We will also fix the "Midnight Bug" where the KIS API returns empty for today's date if queried before market open, by recursively paginating backwards to the previous day at 15:30.

## Architecture Decisions
- **Unified Scheduler**: A single loop (`run_minute_ohlcv_scheduler`) replaces the two-pronged approach. This reduces complexity and bug surface area.
- **Overlap-Aware Early Exit**: `process_ticker` will fetch data and check if the oldest timestamp in the fetched chunk is `<= last_datetime`. If it is, the gap is bridged, and it breaks immediately. This reduces real-time polling to exactly 1 API call per ticker.
- **Empty DataFrame Fallback**: When the KIS API returns empty (e.g., querying 01:00 AM on a new day), the loop will not break. Instead, it will set the target date to `yesterday` and the target time to `15:30:00`, then continue looping to fetch the previous day's data.
- **Unrestricted Midnight Execution**: The scheduler's sleep block (which previously paused everything until 08:55) will be lifted so the unified scheduler can run its historical backfill during the night.

## Task List

### Phase 1: Overlap-Aware Core Logic
- [ ] Task 1: Update `process_ticker` in `app/tasks/minute_ohlcv_scheduler.py`
  - Restore `max_steps=15` as the default.
  - Fix the midnight bug: if `df.empty`, decrement `target_date` by 1 day, set `target_time="153000"`, and `continue` instead of `break`.
  - Implement Early Exit: if `df["dt_str"].min() <= last_datetime`, filter the dataframe to `> last_datetime`, save, and `break`.

### Checkpoint: Foundation
- [ ] Verify that `process_ticker` handles an empty database (fetches up to 3 days).
- [ ] Verify that `process_ticker` handles a populated database (fetches only 1 call and exits).

### Phase 2: Refactoring and Clean Up
- [ ] Task 2: Remove `run_minute_backfill_task` from `app/tasks/minute_ohlcv_scheduler.py`.
- [ ] Task 3: Update `app/core/bootstrap.py` to remove the background task creation for backfilling.
- [ ] Task 4: Update `SystemScheduler` in `app/core/scheduler.py` (if necessary) to ensure the unified minute scheduler runs properly. (Wait, the minute scheduler is run via an asyncio background loop in `bootstrap.py` actually! Let's check `bootstrap.py` to ensure it just starts the normal `start_minute_scheduler_task()`.)

### Checkpoint: Complete
- [ ] No backfill task remains.
- [ ] Unified scheduler runs flawlessly.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Infinite Loop on Delisted Stocks | Low | `max_steps=15` guarantees the loop will terminate even if no data is found after 15 days of stepping backwards. |
| DB Write Lock Contention | Medium | `asyncio.Queue` worker count remains at 50, which was already proven stable with SQLite WAL mode. |
