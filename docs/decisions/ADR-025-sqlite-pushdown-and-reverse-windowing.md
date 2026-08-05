# ADR-025: SQLite Ticker Push-down and Reverse Windowing Optimization

## Status
Accepted

## Date
2026-08-05

## Context
ADR-024를 통해 도입된 쿼리 옵티마이저(비용 기반 재정렬 및 Short-circuit)는 스크리너 엔진의 프론트엔드-투-백엔드 워크플로우를 극적으로 개선했습니다. 그러나 순수 SQLite 내부의 연산 과정에서는 여전히 1GB RAM (Oracle Cloud) 환경에서 OOM 및 병목을 유발할 수 있는 두 가지 치명적인 비효율성이 존재했습니다.

1. **Push-down 누락 (Full Table Scan)**: 파이썬 단에서는 이전 필터(예: 외인 순매수 상위 30선)로 인해 Ticker 집합이 30개로 줄어들었음에도 불구하고, 다음 파이프라인의 DB 쿼리 내 `active_tickers` CTE에는 이 정보가 전달되지 않았습니다. 즉, 2,400개 전 종목을 모두 읽고 윈도우 함수를 돌린 후 파이썬 단에서 최종 교집합(`&`)을 통해 2,370개를 버리는 낭비가 발생하고 있었습니다.
2. **양방향 정렬(Bi-directional Sorting) 오버헤드**: `recent_data` CTE에서 데이터를 자르기 위해 시간 내림차순(`date DESC`)으로 정렬하고(`rn` 번호 부여), 직후 `calc_ma` CTE에서 이평선을 구하기 위해 다시 오름차순(`date ASC`)으로 재정렬하고 있었습니다. 1GB 메모리 환경에서 인메모리 재정렬(Temp B-Tree)이 반복되면 성능 스파이크가 발생합니다.

## Decision

### 1. Ticker 주입(Push-down) 강제화
스크리너 파이프라인의 `_execute_filter` 단계에서, 현재까지 살아남은 `current_tickers` (Set)를 쿼리 문자열 조립 시 `WHERE ticker IN ('...', ...)` 형태로 직접 주입합니다.
- 결과: 가벼운 API 기반 필터 이후에 배치된 DB 연산은 스캔해야 할 종목 수가 2,400개에서 30개 미만으로 극적으로 줄어듭니다.

### 2. 단방향 윈도우 (Reverse Windowing) 최적화 적용
DB 연산의 모든 정렬 기준을 최초 추출 시점의 내림차순 인덱스 번호인 `rn ASC` (최신이 1번, 과거가 N번) 하나로 통일합니다.
- `ORDER BY date ASC ROWS BETWEEN N PRECEDING AND CURRENT ROW` 구문을 폐기하고, **`ORDER BY rn ASC ROWS BETWEEN CURRENT ROW AND N FOLLOWING`** 구문을 도입합니다. (수학적으로 두 윈도우에 속한 데이터와 통계값은 정확히 일치함)
- `ma_cross` 구문의 과거 데이터 추적을 위한 `LAG(..., 1)` 윈도우 함수 역시 `LEAD(..., 1)`로 교체합니다.

## Alternatives Considered
### 1. SQLite LATERAL JOIN (Push-down 대안)
- SQLite는 LATERAL 키워드를 공식 지원하지 않아 조인 기반의 파티션 튜닝에 제약이 많으므로, 파이썬에서 `IN` 절로 동적 주입하는 것이 가장 확실하고 이식성 높습니다. (Accepted)
### 2. Pandas 연산 위임 (Reverse Window 대안)
- DB에서는 단순히 RAW 데이터를 뽑고 파이썬 Pandas를 이용해 이동평균선 정렬/계산을 수행하는 방안.
- 1GB RAM 환경에서는 Pandas DataFrame 할당 자체가 치명적이므로(Set-Theory 파이프라인 도입 원인), 끝까지 DB 단(Push-down)에서 해결하는 것이 맞습니다. (Rejected)

## Consequences
- **극단적인 속도 향상**: 가장 무거운 Minute Stress Test(최대 윈도우 분봉 쿼리)가 16.5초에서 **2.4초**로 단축되었습니다 (로컬 벤치마크 기준).
- **메모리 안정성**: SQLite 엔진이 데이터를 읽어 윈도우 함수를 처리할 때 단 한 번의 정렬(Sort) 파티셔닝만 수행하므로 클라우드 환경에서 Swap(Disk I/O)이 유발될 확률을 제로에 가깝게 만들었습니다.
