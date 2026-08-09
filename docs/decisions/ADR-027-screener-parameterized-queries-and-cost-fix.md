# ADR-027: Parameterized Queries and Heuristic Cost Fix in Screener

## Status
Accepted

## Date
2026-08-09

## Context
스크리너 서비스(`screener_service.py`)의 쿼리 최적화 과정에서 두 가지 심각한 성능 병목 및 논리적 오류가 발견되었습니다.

1. **SQL 파서 오버헤드 (String Literal Injection)**: 이전 필터 단계에서 살아남은 종목 집합(`current_tickers`)을 다음 DB 쿼리로 넘길 때(Push-down), Python 단에서 `", ".join(f"'{t}'" for t in current_tickers)` 형태로 최대 2,400개의 종목 코드를 하나의 거대한 문자열로 만들어 `WHERE ticker IN (...)` 구문에 꽂아 넣고 있었습니다. 이는 SQLite 파서에 엄청난 메모리 오버헤드와 지연을 유발하며, SQL Injection 관점에서도 안티 패턴입니다.
2. **휴리스틱 비용(Cost) 옵티마이저 버그**: `ADR-026`을 통해 이동평균선(MA) 연산이 Python 스케줄러로 위임되어 DB에는 이미 연산이 끝난 `ma20`, `ma60` 컬럼이 존재합니다. 따라서 쿼리는 과거 60일 치 캔들을 모두 읽어올 필요 없이 `duration` 또는 `within` 일수(보통 1~5)만큼만 캔들을 조회하면 됩니다. 하지만 `_estimate_cost` 함수는 여전히 과거의 아키텍처에 머물러 `max_window + duration`으로 비용을 과대 계상(`k`)하고 있었으며, 이로 인해 옵티마이저가 MA 필터를 무거운 연산으로 착각하여 실행 순서를 잘못 배정하는 문제가 있었습니다.

## Decision

### 1. 동적 파라미터화 (Parameterized Queries) 도입
모든 스크리너 DB 필터 핸들러(`_handle_ma_alignment`, `_handle_ma_cross` 등)에서 하드코딩된 문자열 주입을 제거하고, `IN (?, ?, ...)` 형태의 Parameterized Query로 교체했습니다.
- `placeholders = ", ".join("?" for _ in current_tickers)`
- `ma_conn.execute(query, tuple(current_tickers))`
이를 통해 수천 개의 Ticker가 넘어가더라도 파싱 속도 저하 없이 안전하고 빠르게 쿼리가 실행됩니다. (SQLite 최신 버전의 `SQLITE_MAX_VARIABLE_NUMBER` 32766 제한 하에 안전함)

### 2. 휴리스틱 비용(Cost) 계산 로직 현실화
`_estimate_cost` 함수 내에서 `max_window` 조회 로직을 완전히 삭제하고, 오직 실제로 디스크/메모리에서 읽어오는 스캔 양인 `duration` 및 `within + 1` 값만을 `k` (Required Rows) 상수로 사용하도록 수정했습니다.

## Consequences
- **파싱 오버헤드 제거**: 극단적인 상황(2,400개 종목을 그대로 IN 절에 넘길 때)에서의 DB 락 및 파싱 지연 시간이 완벽하게 해소되었습니다.
- **파이프라인 최적화**: MA 관련 필터들의 비용이 정상적으로 매우 낮게 산정되어, 쿼리 옵티마이저가 랭킹 API 다음으로 가장 효율적인 순서에 MA 필터를 배치하게 되어 전체 스크리닝 체결 속도가 비약적으로 상승했습니다.
