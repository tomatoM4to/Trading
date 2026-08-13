- [x] Task: Document & Setup schemas
  - Acceptance: `docs/screener.md` is updated with API parameter documentation for `disparity_value` and `volume_peak_breakout`.
  - Verify: Manual read of `docs/screener.md`.
  - Files: `docs/screener.md`

- [x] Task: Implement `disparity_value` AST parser
  - Acceptance: `ScreenerEngine._handle_disparity_value` is added, properly validates `line` against `VALID_MA_PERIODS`, validates `direction` (above/below) and `threshold`, ATTACHes the MA db, and executes the SQL query.
  - Verify: Pytest or manual testing.
  - Files: `app/services/screener_service.py`

- [x] Task: Implement `volume_peak_breakout` AST parser
  - Acceptance: `ScreenerEngine._handle_volume_peak_breakout` is added, translates preset lookbacks (1M, 3M, 2H, 4H) into integer days/minutes, uses `ORDER BY volume DESC LIMIT 1` scalar subquery to find high price, and checks if current close > high.
  - Verify: Pytest or manual testing.
  - Files: `app/services/screener_service.py`
