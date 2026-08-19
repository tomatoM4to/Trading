# ADR-033: Screener AST Injection Prevention via Strict Validation

## Status
Accepted

## Date
2026-08-13

## Context
Our dynamic screener pipeline (ADR-014) translates frontend-generated AST requests directly into SQLite queries executed against our in-memory MA database (`daily_ma`, `minute_ma`). 

During an extensive code audit, a vulnerability was identified in `screener_service.py`. The AST parser previously extracted the moving average column name using string interpolation without strict bounds checking:
`f"ma{line.split('_')[-1]}" if line.startswith("ma_daily_") else line`

This approach posed a significant AST Injection vulnerability. If a malicious or malformed string (e.g., `'5); DROP TABLE daily_ma; --'`) was passed in the `line` or `duration` parameters via the JSON request, it could be directly interpolated into the SQLite execution context, leading to unauthorized data manipulation or server crashing (Denial of Service), which is catastrophic for our 1GB RAM in-memory architecture.

## Decision
We decided to implement rigorous input validation constraints directly within the `ScreenerEngine`:
1. **Column Mapping Constraint**: All MA period inputs (e.g., `5`, `10`, `ma_daily_5`) must match exactly against a pre-defined static allowlist: `VALID_MA_PERIODS = {"5", "10", "20", "60", "120", "200"}`.
2. **Type and Bound Checking**: Timeframe bounds (like `duration` or `within`) must be strictly cast as `int` and validated to fall within `1` to `500` before any SQL query generation occurs.

## Alternatives Considered
### Parameterized Queries (Binding `?`) for Column Names
- Pros: Standard SQL injection defense.
- Cons: SQLite (and most SQL engines) does not allow parameter binding for column names or identifiers (only for values).
- Rejected: Technically impossible for dynamic column selection.

### ORM (e.g., SQLAlchemy)
- Pros: Built-in query builders handle identifier quoting safely.
- Cons: High memory overhead and performance penalties, violating our Zero-Latency strict performance budgets (ADR-022, ADR-027).
- Rejected: Too heavy for the 1 OCPU/1GB RAM constraint.

## Consequences
- Total immunity against SQL/AST injection through the screener JSON body.
- Invalid requests instantly return 400 Bad Request, saving DB parsing overhead (Fail-fast).
- Any future MA windows (e.g., 240-day) must be explicitly added to `VALID_MA_PERIODS` in the code, slightly increasing maintenance overhead but guaranteeing security.
