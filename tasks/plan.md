# Plan: Screener Ranking View (Multi-Factor)

## 1. Components & Dependencies
- **Backend (`app/services/screener_service.py`)**:
  - `_fetch_investor_rank`: Needs to enumerate the list of unique tickers and assign `1.0, 2.0, ...` instead of `0.0`.
- **Frontend (`web/components/screener/ScreenerResultTable.tsx`)**:
  - Toggle state: `viewMode` ('default' | 'ranking').
  - AST Parsing: Extract filter node IDs and their types from the original AST payload to determine column headers and sorting directions.
  - Rank Computation: Function to calculate standard competition ranking per column and average rank per row.

## 2. Implementation Order
1. **Backend Patch**: Modify `_fetch_investor_rank` to return actual ranks.
2. **Backend Verification**: Run `benchmark_screener.py` (specifically Heavy 5) to verify ranks `1.0` through `30.0` appear in the `filter_values`.
3. **Frontend AST Context**: Ensure the AST structure (used to execute the query) is accessible within the table component to derive filter names/types.
4. **Frontend Rank Engine**: Implement the `computeRanks` utility and apply it to the data payload upon receiving the `complete` event.
5. **Frontend UI/UX**: Build the toggle button, dynamic table headers, and map the ranks into the table cells with proper styling.

## 3. Risks & Mitigations
- **Risk**: Frontend doesn't know what "ast-node-1234" means (is it an alignment filter or a cross filter?).
  - **Mitigation**: The frontend built the AST, so it must pass the AST metadata or parse it locally to map `ast-node-1234` to its type (`ma_cross`) to determine the correct sort direction (`desc`).
- **Risk**: A ticker is missing a filter value (e.g. somehow bypassed or short-circuited).
  - **Mitigation**: Handle `undefined` gracefully by assigning the lowest possible rank.

## 4. Parallel vs Sequential
- **Sequential**: Backend must be patched first so we can generate valid mock/live data to test the frontend. Frontend AST context parsing must precede the Rank Engine computation.

## 5. Verification Checkpoints
- **Checkpoint 1**: Backend returns `{ticker: {filter_id: 1.0}}` for foreign net buy.
- **Checkpoint 2**: Frontend correctly logs the computed ranks in the console without crashing.
- **Checkpoint 3**: UI displays the toggle, switches views smoothly, and the table sorts perfectly by Average Rank.
