# Implementation Plan: Strict MA Count Check

## Objective
Update moving average calculations in `screener_service.py` and `market_service.py` to return `NULL` if the required number of candles is not met, using SQLite window functions.

## Implementation Details

1.  **`screener_service.py` (`_handle_ma_uptrend`)**:
    *   Currently, the dynamic SQL builds `AVG(...) OVER(...) as maX`.
    *   Change this to: `CASE WHEN COUNT(...) OVER(...) = N THEN AVG(...) OVER(...) ELSE NULL END as maX`.
    *   The `HAVING` clause `SUM(maX_up) = days` will automatically filter out rows where `maX` is `NULL` (since `NULL > ...` is `NULL`, and `SUM` won't meet the target).

2.  **`market_service.py` (`get_chart_data`)**:
    *   Update the `daily_ma` CTE and the main query for `minute_ma`.
    *   Change every `AVG(...)` to the `CASE WHEN COUNT(...) = N THEN AVG(...) ELSE NULL END` format.
    *   This ensures the chart data (open, high, low, close) is still returned for every candle, but the MA fields will explicitly be `NULL` if the candle count is insufficient.

## Verification
*   Test `/admin/live/global-status` or chart viewer to ensure no crashes.
*   Check a new stock to verify `null` values for long MAs.
