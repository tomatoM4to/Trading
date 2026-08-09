# Todo: Screener Ranking View

- [ ] Task: Update `_fetch_investor_rank` in `app/services/screener_service.py`.
  - Acceptance: The function enumerates the unique tickers and assigns `index + 1` (as float) instead of `0.0`.
  - Verify: Run `uv run python scripts/benchmark_screener.py` and inspect Heavy 5's output payload to ensure `foreign_net_buy_rank` values are `1.0`, `2.0`, etc.
  - Files: `app/services/screener_service.py`

- [ ] Task: Setup Frontend State and AST Parsing in `ScreenerResultTable.tsx`.
  - Acceptance: The component maintains a `viewMode` state and maps each AST node ID to its filter `type` so it knows the sorting direction (e.g., `ma_cross` -> `desc`).
  - Verify: Build the frontend `cd web && npm run build` and ensure no type errors.
  - Files: `web/components/screener/ScreenerResultTable.tsx`, `web/types/screener.ts` (if needed).

- [ ] Task: Implement Rank Computation Engine.
  - Acceptance: Given the items and AST mapping, compute individual integer ranks per filter (handling ties) and an overall average rank.
  - Verify: Log the computed `rankedItems` to the browser console and manually verify the math.
  - Files: `web/components/screener/ScreenerResultTable.tsx`, `web/lib/ranking.ts` (or similar utility file).

- [ ] Task: Build Ranking View UI.
  - Acceptance: A toggle button exists. In Ranking View, dynamic columns show up (one per filter + Final Average Rank). The table is sorted by Final Rank.
  - Verify: visually confirm in the browser that the table switches correctly and sorting works.
  - Files: `web/components/screener/ScreenerResultTable.tsx`
