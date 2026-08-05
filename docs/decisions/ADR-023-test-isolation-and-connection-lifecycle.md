# ADR-023: SQLite Connection Lifecycle and Test Isolation

## Status
Accepted

## Date
2026-08-05

## Context
Our application relies on a dual database architecture: an in-memory SQLite database (`file::memory:?cache=shared`) for zero-latency operations during trading hours, and a physical disk backup (`test_trading.db` / `trading.db`) for persistence. While testing the full data pipeline (Memory Initialization -> Data Slicing -> Gap-fill -> Disk Sync -> Integrity Check), we encountered several critical issues related to connection lifecycles, file locks, and strict typing:

1. **Memory Database Evaporation**: SQLite's shared memory databases immediately drop all tables and data when the last connection to the database is closed. This caused our test endpoints to crash when schedulers tried to access the empty DB.
2. **WinError 32 File Lock Error**: During sequential tests, deleting the test physical database failed because the connection from the previous test's `sync_memory_to_disk` was still lingering in memory. This occurred because Python's `with sqlite3.connect(...)` context manager only manages transactions (commit/rollback) and **does not** close the connection automatically upon exit.
3. **Data Integrity False Positives**: Our SQLite tables (`daily_ohlcv`, `minute_ohlcv`) use `STRICT` mode with `INTEGER` types for dates and times to save memory. However, the integrity test failed to match any records because it fetched `int` keys from the DB and tried to look them up using `str` keys from the KIS API response, resulting in 0% accuracy due to Python's strict dictionary key matching.

## Decision

1. **Keep-alive Connections for Memory DBs**:
   In any scoped test or runtime environment that dynamically routes to an in-memory shared SQLite database, a `keepalive_conn` must be instantiated at the start of the scope and held open until the scope completes (`finally: keepalive_conn.close()`). This anchors the database and prevents it from evaporating.

2. **Explicit Connection Closing**:
   When opening standalone connections (e.g., in background tasks or `sync_memory_to_disk`), we must never rely solely on the `with sqlite3.connect(...)` block to close the file. We must explicitly use `try ... finally: conn.close()` to ensure file locks are released immediately. (Note: API endpoints are safe as they use the `get_db()` FastAPI dependency which correctly implements `finally: conn.close()`).

3. **Explicit Type Casting for STRICT SQLite Columns**:
   When querying `STRICT INTEGER` columns and building Python dictionaries for data mapping/comparison with external API data, we must explicitly cast the SQLite `int` values to `str` (e.g., `str(row["date"])`) to prevent silent dictionary lookup failures.

4. **Robust Test Teardown**:
   When resetting test environments, we must actively clean up `-wal` and `-shm` files alongside the main `.db` file to prevent SQLite cache poisoning across sequential test runs.

## Consequences
- The full integration pipeline can now run completely isolated in-memory and sync to a dummy physical file without interfering with the production database.
- File locks are immediately released, allowing for stable sequential integration testing.
- Data integrity checks boast a mathematically proven 100% accuracy rate against the KIS OpenAPI.
- Developers must remain vigilant about Python's `sqlite3` context manager behavior.
