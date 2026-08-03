# ADR-020: Screener Pre-filter Optimization (SQLite Partition Reduction)

## Status
Accepted

## Date
2026-08-03

## Context
현재 스크리너 엔진은 1GB RAM 환경의 메모리 제약을 피하고자, 2,400여 개 전 종목에 대한 이평선 계산 등 무거운 기술적 지표 연산을 파이썬이 아닌 SQLite 내부의 윈도우 함수(`ROW_NUMBER`, `AVG` 등)와 CTE를 통해 처리하고 있습니다(Push-down).

문제는 기존 구조에서는 거래 정지(Halted)나 관리 종목(Admin Issue)처럼 실제 자동 매매가 불가능한 종목들에 대해서도 `daily_ohlcv` 및 `minute_ohlcv` 테이블을 풀 스캔하여 윈도우 함수 파티셔닝과 이평선 계산을 수행한다는 점입니다. 이는 한정된 OCPU 및 메모리 자원을 크게 낭비하며 스크리너 응답 속도를 저하시키는 주요 원인이었습니다.

이러한 불필요한 종목을 파이프라인의 어느 단계에서 제외(Filter)할 것인지에 대한 결정이 필요했습니다.

## Decision
**SQLite 내부 쿼리 단에서 CTE 조인을 통해 사전 필터링(Pre-filter)을 수행**하여 윈도우 함수가 처리할 파티션 모수를 원천적으로 축소합니다.

파이썬 스크리너 엔진(`ScreenerEngine`)에서 최종적으로 교집합(`&`)을 구하기 전 파이썬 레벨에서 필터링하는 방식(Post-filter)을 기각하고, 모든 스크리너 개별 쿼리(`ma_alignment`, `ma_cross`, `ma_convergence` 등) 상단에 다음과 같은 공통 CTE 패턴을 주입하여 `daily_ohlcv` 등 메인 테이블과 조인(JOIN)하도록 강제합니다.

```sql
WITH active_tickers AS (
    SELECT ticker FROM stock_codes 
    WHERE is_halted = 0 AND is_admin_issue = 0
)
...
JOIN active_tickers a ON d.ticker = a.ticker
```

(단기과열 `is_overheated` 및 투자경고 `is_warning` 종목은 매매가 가능하므로 제외 대상에 포함하지 않습니다.)

## Alternatives Considered

### Python-level Filtering (Post-filter)
- Pros: 기존 작성된 복잡한 SQL 쿼리들을 전혀 수정할 필요 없이 파이썬 로직 한 줄만 추가하면 됨.
- Cons: DB 내에서는 여전히 2,400개 전 종목을 대상으로 무거운 윈도우 함수 연산이 돌아가므로 컴퓨팅 리소스 절감 효과가 전혀 없음. 단순한 "눈가림"에 불과함.
- Rejected: 실전 환경(PROD)에서의 진정한 성능 최적화를 위해 기각함.

## Consequences
- 윈도우 함수 연산 대상이 2,400여 개에서 2,000여 개(정상 종목)로 약 15~20% 감소하여 실질적인 DB 쿼리 실행 속도 향상.
- 향후 신규 스크리너 지표(SQL 쿼리)를 추가할 때마다 반드시 `active_tickers` CTE 조인 패턴을 반복 작성해야 하는 규칙(Boilerplate)이 생김. (`AGENTS.md`에 명문화하여 방어)
- 프론트엔드나 스크리너 최종 반환 규격(AST, Payload)에는 어떠한 영향도 주지 않음.
