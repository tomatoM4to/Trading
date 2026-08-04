# ADR-022: In-Memory Database and STRICT Schema Optimization

## Status
Accepted

## Date
2026-08-04

## Context
Our FastAPI trading server relies heavily on complex SQLite queries (such as moving average calculations using window functions) to filter and screen stocks. As the dataset grows, disk I/O and query execution times for these complex operations become a significant bottleneck, especially given our strict memory limit (1GB RAM) and the goal of a Zero-Latency Breakout system.

We also observed that SQLite's automatic index generation (via implicit ROWID) and dynamic typing (where integers could be stored as strings) were unnecessarily ballooning the database file size and cache footprint. Specifically:
- Explicit B-Tree indexes on already-indexed composite primary keys were wasting space.
- Date and Time columns were stored as `TEXT` instead of `INTEGER`, taking up more space and causing slower string-based comparisons in queries.
- Operations utilizing temp tables or sorting were spilling to disk, increasing latency.

## Decision
1. **In-Memory Shared Cache Architecture**: We shifted from a purely file-backed SQLite database to an In-Memory shared database (`file::memory:?cache=shared`). The physical DB is loaded into memory via `sqlite3.Connection.backup()` at startup. To prevent SQLite from aggressively garbage-collecting the anonymous shared memory database when all transient connections close, a global `_keepalive_conn` is held open for the lifetime of the process.
2. **Memory Temp Store**: We enforced `PRAGMA temp_store = MEMORY` to guarantee that all intermediate sorting and temporary B-trees are kept entirely in RAM.
3. **WITHOUT ROWID & STRICT Tables**: All primary tables (`daily_ohlcv`, `minute_ohlcv`, `stock_codes`) were recreated with `WITHOUT ROWID` and `STRICT` modifiers. This collapses the primary key index and table data into a single clustered index, saving roughly 297MB of redundant B-Tree indexes, and enforces strict typing to prevent space waste.
4. **INTEGER Date/Time**: We migrated `date` and `time` columns from `TEXT` to `INTEGER`. For `time` comparisons to remain accurate in SQL string concatenations (e.g., `MAX(date || time)`), we implemented zero-padding in queries via `printf('%06d', time)`.

## Alternatives Considered
### 1. Fully File-Backed DB with Aggressive Caching
- **Pros:** Data persistence is guaranteed on every write.
- **Cons:** High I/O overhead for complex window queries on low-tier cloud instances (Oracle Cloud 1 OCPU/1GB). Disk latency directly impacted the screener's performance.
- **Rejected:** The requirement for Zero-Latency screener execution outweighed the need for synchronous disk writes, especially since raw KIS data can always be re-fetched.

### 2. Loading Data into Pandas DataFrames instead of In-Memory DB
- **Pros:** Pandas is highly optimized for vectorized operations.
- **Cons:** Loading 2,400 tickers into Pandas all at once violates our 1GB RAM Set-Theory Pipeline constraint (ADR-014).
- **Rejected:** SQLite's query optimizer handles data filtering much more memory-efficiently than holding raw DataFrames in memory.

## Consequences
- **Performance:** Complex screener queries now run completely in RAM with zero disk I/O, providing near-instantaneous execution times.
- **Storage:** The physical DB size was drastically reduced due to the removal of ROWIDs, redundant explicit indexes, and the switch to INTEGER dates/times.
- **Volatility:** Writes performed by the background scheduler are currently only committed to the In-Memory database. If the server restarts, any data fetched during that session is lost until it is re-fetched by the bootstrap pipeline. A background disk-sync mechanism may be considered in the future if persistence becomes critical.
- **Code constraints:** SQL queries interacting with the `time` column must use `printf('%06d', time)` to prevent zero-truncation bugs during string concatenation.
