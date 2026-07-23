## Task 1: Update `process_ticker` for mode control
**Description:** Modify `process_ticker` in `minute_ohlcv_scheduler.py` to accept `limit_days` (default 3) and `max_steps` (default 15). This allows us to control how deep into the past the function looks, preventing infinite looping or excessive API calls.

**Acceptance criteria:**
- [ ] `process_ticker` accepts `limit_days` and `max_steps`
- [ ] The API loop respects `max_steps` instead of the hardcoded `15`
- [ ] The API loop breaks early if `target_date` is older than `now - limit_days`

**Dependencies:** None
**Files likely touched:** `app/tasks/minute_ohlcv_scheduler.py`
**Estimated scope:** Small

---

## Task 2: Create `run_minute_backfill_task`
**Description:** Implement a new function in `minute_ohlcv_scheduler.py` that iterates through all active tickers exactly once using a queue/worker model, calling `process_ticker` with `max_steps=15, limit_days=3`.

**Acceptance criteria:**
- [ ] Exists as a standalone async function
- [ ] Loads all active tickers from SQLite
- [ ] Spawns worker tasks to process the queue
- [ ] Exits gracefully after the queue is empty

**Dependencies:** Task 1
**Files likely touched:** `app/tasks/minute_ohlcv_scheduler.py`
**Estimated scope:** Medium

---

## Task 3: Optimize `run_minute_ohlcv_scheduler`
**Description:** Update the existing real-time scheduler loop so that it calls `process_ticker` with `max_steps=1`. It no longer needs to do deep backfilling because Task 2 handles it.

**Acceptance criteria:**
- [ ] Calls `process_ticker(..., max_steps=1)`
- [ ] Retains its market-hours `09:00~15:55` while loop and sleep mechanisms

**Dependencies:** Task 1
**Files likely touched:** `app/tasks/minute_ohlcv_scheduler.py`
**Estimated scope:** Small

---

## Task 4: Integrate with `bootstrap.py`
**Description:** Modify the bootstrap pipeline so that it unconditionally fires the backfill task in the background, and conditionally fires the real-time scheduler if within market hours.

**Acceptance criteria:**
- [ ] `asyncio.create_task(run_minute_backfill_task())` is always called
- [ ] The existing real-time scheduler condition (`09:00 <= now < 15:55`) remains intact

**Dependencies:** Task 2, Task 3
**Files likely touched:** `app/core/bootstrap.py`
**Estimated scope:** Small

---

## Task 5: Fix `admin_test_service.py` (if necessary)
**Description:** Ensure that the integration tests for the minute scheduler in `admin_test_service.py` are updated to account for the decoupled architecture (e.g., calling the backfill task directly to test gap recovery).

**Acceptance criteria:**
- [ ] `test_minute_scheduler_integration_service` passes or logic is updated to reflect the new gap-fill behavior

**Dependencies:** Task 4
**Files likely touched:** `app/services/admin_test_service.py`
**Estimated scope:** Medium
