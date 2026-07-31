- [x] Task 1: Update `screener_service.py`
  - Acceptance: `_handle_ma_uptrend` dynamically generates `CASE WHEN COUNT() = N` logic for all MAs.
  - Verify: Run `uv run ruff check` and `fastapi dev` syntax check.
  - Files: `app/services/screener_service.py`

- [x] Task 2: Update `market_service.py`
  - Acceptance: `get_chart_data` uses `CASE WHEN COUNT() = N` for both `daily_ma` and `minute_ma` CTEs.
  - Verify: Run `uv run ruff check` and `fastapi dev` syntax check.
  - Files: `app/services/market_service.py`
