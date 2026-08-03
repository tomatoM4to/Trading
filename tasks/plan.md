# 스크리너 쿼리 최적화 계획 (Pre-filter)

## 1. 개요
스크리너 파이프라인에서 무거운 윈도우 함수 연산을 수행하기 전, `stock_codes` 테이블을 조인하여 거래정지(`is_halted=1`) 및 관리종목(`is_admin_issue=1`)을 사전 제외(Pre-filter)함으로써 DB 리소스 낭비를 막고 검색 속도를 향상시킵니다. 단기과열이나 투자경고 종목은 매매가 가능하므로 필터링하지 않습니다.

## 2. 작업 대상
`app/services/screener_service.py` 내의 다음 4가지 핸들러 메서드의 내부 SQLite 쿼리:
1. `_handle_ma_alignment`
2. `_handle_ma_cross`
3. `_handle_ma_convergence_consolidation`
4. `_handle_ma_convergence_point`

## 3. 구현 전략
각 쿼리의 `WITH` 절 맨 위에 `active_tickers` CTE를 추가합니다.
```sql
WITH active_tickers AS (
    SELECT ticker FROM stock_codes 
    WHERE is_halted = 0 AND is_admin_issue = 0
),
recent_data AS (
    SELECT * FROM (
        SELECT d.*,
               ROW_NUMBER() OVER(PARTITION BY d.ticker ORDER BY d.date DESC) as rn
        FROM {table_name} d
        JOIN active_tickers a ON d.ticker = a.ticker
    ) WHERE rn <= {required_rows}
)
```
이렇게 하면 윈도우 함수(`ROW_NUMBER`, `COUNT`, `AVG` 등)가 평가될 파티션(종목)의 개수가 근본적으로 감소하여 속도 및 메모리 이점이 발생합니다.
