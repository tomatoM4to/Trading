# Implementation Plan: Fix GC SQL Bug & Add Manual GC Endpoint

## Overview
We need to fix a critical SQL syntax error in the daily Garbage Collector where it queried a non-existent `code` column instead of the correct `ticker` column. Additionally, we need to expose a new endpoint in the admin router to explicitly trigger this GC process on-demand.

## Architecture Decisions
- Add a new endpoint to the admin router (`app/routes/admin.py`). We will use a `POST /admin/action/gc` endpoint for triggering the action.
- The endpoint will reuse the existing `cleanup_ohlcv_job()` logic from `SystemScheduler` to ensure it follows the exact same logic (Chunking GC) as the scheduled task.

## Task List

### Phase 1: Fix GC SQL Bug
- [ ] Task 1: Fix column name in `app/core/scheduler.py`. Change `SELECT code FROM stock_codes` to `SELECT ticker FROM stock_codes`.

### Phase 2: Add Manual GC Endpoint
- [ ] Task 2: Add the endpoint to `app/routes/admin.py` which will invoke `SystemScheduler().cleanup_ohlcv_job()`.

## Checkpoint: Complete
- [ ] Ensure the syntax is correct.
- [ ] Check if the endpoint is properly hooked up to the FastAPI router.
