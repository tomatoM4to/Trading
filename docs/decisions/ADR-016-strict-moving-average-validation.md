# ADR-016: Strict Moving Average Validation via SQLite Push-down

## Status
Accepted

## Date
2026-08-01

## Context
Our trading system relies heavily on Moving Averages (e.g., MA20, MA60, MA120) to detect uptrends and convergence signals. We use an "SQLite Push-down" strategy (ADR-014) to compute these technical indicators directly in the database using Window Functions (`AVG() OVER ...`), avoiding the OOM risk of fetching data into Python/Pandas on our 1GB RAM server.

However, a critical logical flaw was discovered: if a stock lacked sufficient data (e.g., a newly listed stock with only 5 days of data), the simple `AVG(close) OVER (ROWS BETWEEN 59 PRECEDING AND CURRENT ROW)` would still execute without error. It would calculate the average of the available 5 days and present it as the "60-day MA." This caused "False Positive" trading signals, tricking the screener into thinking a non-existent long-term moving average was broken or trending upwards.

## Decision
We enforce a **Strict Moving Average Validation** rule directly within the SQL queries across both the Screener (`screener_service.py`) and the Chart Viewer (`market_service.py`). 

Instead of a simple `AVG`, we now wrap all moving average calculations with a strict candle count check:
```sql
CASE 
    WHEN COUNT(close) OVER (ORDER BY date ASC ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) = 60 
    THEN AVG(close) OVER (ORDER BY date ASC ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) 
    ELSE NULL 
END as ma_60
```

## Alternatives Considered
- **Python/Pandas Post-processing (`if len(data) < N:`)**: 
  - *Cons:* Requires fetching millions of rows into Python memory before filtering, immediately violating our 1GB RAM constraint.
  - *Rejected:* We must stick to the SQLite Push-down architecture.
- **Filtering rows in SQL (`WHERE row_num >= 60`)**:
  - *Cons:* This filters out the entire row (candle data) for the first 59 days. While acceptable for the Screener, it completely breaks the Chart Viewer, which needs to render the early price candles even if the 60-MA hasn't formed yet.
  - *Rejected:* We need a solution that preserves the candle data while explicitly nullifying the invalid moving average.

## Consequences
- **Zero False Positives:** The Screener logic (e.g., `ma60_up`) will evaluate `NULL > LAG(NULL, 1)`, resulting in `NULL`. The `HAVING SUM(ma60_up) = days` will automatically exclude these stocks without requiring complex IF statements in Python.
- **Frontend Contract:** The Chart Viewer API now accurately returns `null` for unformed moving averages. The frontend must implement logic to skip drawing lines for `null` data points without crashing.
- **Maintained Performance:** The `COUNT()` window function adds negligible overhead to the SQLite engine, keeping our operations blazingly fast.
