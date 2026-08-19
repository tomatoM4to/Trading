# ADR-015: Shift to Time-based Bulk GC (Garbage Collection)

## Status
Superseded by ADR-031 (Intelligent GC & Smart Trigger)

## Date
2026-08-01

## Context
Our Oracle Cloud Free Tier instance (1 OCPU, 1GB RAM) faces strict constraints. We previously adopted a "For-Loop Chunking" Garbage Collection (ADR-003) strategy to prevent SQLite Database Locks and Out of Memory (OOM) errors during the nightly cleanup at 23:00. This method maintained exactly 500 daily candles and 1560 minute candles per ticker by iterating over all 2,400 tickers and executing multiple queries for each.

However, as the system ran in production, two major flaws emerged:
1. **Severe Performance Bottleneck:** The GC routine executed over 9,600 queries (SELECTs and DELETEs) per night, causing the process to take upwards of 3-10 minutes even on powerful local machines, and posing a risk of system hangs on the 1GB RAM server.
2. **Noise Data Accumulation:** Illiquid stocks ("소외주") that barely trade accumulated "zombie" minute candles over weeks or months to reach the 1560 threshold. These ancient candles completely lose their momentum-trading significance (e.g., a 60-minute moving average built over 2 weeks is trading noise, not a breakout signal) and unnecessarily bloated the database.

## Decision
We are completely deprecating the row-count-based "For-Loop Chunking" GC in favor of a **Pure Time-based Bulk GC**.
- **Daily OHLCV:** Delete all data older than 300 calendar days.
- **Minute OHLCV:** Delete all data older than 7 calendar days.
- **Implementation:** Two simple `DELETE` queries without any Python loops or ticker-by-ticker iterations.

## Alternatives Considered

### Hybrid Strategy (Row-count + Time limit)
- Pros: Ensures a maximum cap on data even for highly liquid stocks while strictly pruning old data.
- Cons: Still requires the heavy Python For-Loop iteration across 2,400 tickers to count rows, failing to solve the core performance bottleneck.

## Consequences
- **Extreme Speed:** The nightly GC now completes in ~0.1 seconds, eliminating CPU/RAM spikes and minimizing DB locks.
- **Storage Optimization:** The database footprint naturally stabilizes. Even for hyper-liquid stocks, 7 days of 1-minute candles (approx. 2,700 rows) is negligible for SQLite.
- **Improved Trading Signal Quality:** By hard-cutting minute data at 7 days, we guarantee that moving averages and other technical indicators are strictly momentum-driven. Illiquid stocks are naturally filtered out by screener liquidity checks rather than being artificially propped up by stale data.
- **Simpler Code:** Maintenance is significantly easier, preventing bugs (like the previous `code` vs `ticker` typo).
- **Note on Disk Space:** The file size of `trading.db` may not physically shrink immediately after deletion due to SQLite's `freelist` mechanism (it reuses the freed space for new incoming data). This is intentional and optimal for performance; a manual `VACUUM` can be used if physical compression is strictly required.
