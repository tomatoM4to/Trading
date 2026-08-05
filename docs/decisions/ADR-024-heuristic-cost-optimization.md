# ADR-024: Heuristic Cost Optimization for Screener Pipeline

## Status
Accepted

## Date
2026-08-05

## Context
기존 스크리너 파이프라인(Dynamic Screener Pipeline, ADR-014 참조)은 클라이언트가 요청한 `filters` 리스트를 들어온 순서대로 순차 실행했습니다. 
그러나 1GB RAM (Oracle Cloud) 제약 하에서 무거운 윈도우 함수(예: 수렴 돌파)를 분봉(Minute) 데이터에 적용하거나, 복잡한 다중 교집합(AND) 요청을 처리할 경우 60초 타임아웃(504 Error)이 빈번하게 발생하여 서버 가용성이 저하되는 문제가 발견되었습니다.

특히 API 기반의 랭킹 필터(예: 외인/기관 순매수 30선)나 가벼운 일봉 필터가 리스트 뒤쪽에 배치될 경우, 앞선 무거운 분봉 필터가 2,400개 전 종목을 무의미하게 전체 스캔(Full Scan)하는 자원 낭비(N+1 병목과 유사)가 주원인이었습니다.

## Decision
DB 엔진 내부의 실행 계획(Execution Plan) 개조나 물리적 스키마 변경 대신, 파이프라인 엔진(Application 레벨)에서 **휴리스틱 시간복잡도(Big O) 기반의 쿼리 옵티마이저(Optimizer)**를 구현하여 필터 실행 순서를 동적으로 재정렬(Reordering)합니다.

1. **Big O 비용(Cost) 모델링 (`_estimate_cost`)**
   - 모든 스크리너 DB 쿼리의 시간복잡도는 `O(T * K * L)`로 정의할 수 있습니다. (T: 탐색 종목 수, K: 캔들 수, L: 이평선 수)
   - API 통신 랭킹 필터: 반환 파티션을 즉시 30개로 축소시키므로 무조건 **Cost = 0**으로 최우선 할당.
   - DB 기반 필터: `Cost = (Max_Window + Duration) * 연산할_이평선_개수 * Table_Weight`
     - Table_Weight(페널티): 일봉(Daily) = 1.0, 분봉(Minute) = 3.0 (B-Tree 인덱스 스캔 깊이 차이 반영)

2. **AST Splitter 및 정렬 (`_optimize_pipeline`)**
   - 클라이언트의 Flat 요청 리스트를 논리 연산자(`OR`)를 기준으로 분할(Split)하여 여러 개의 독립적인 `AND` 체인으로 만듭니다.
   - 각 `AND` 체인 내부의 필터들을 위에서 산출한 Cost 기준으로 오름차순 정렬합니다.

3. **Short-circuit 집합 연산**
   - 가벼운 필터를 통과하여 초기 교집합이 급격히 줄어들면, 후속 무거운 필터들의 연산량이 비례하여 감소합니다.
   - 교집합 연산 중 `Set`이 완전히 비어버릴(Empty) 경우, 남은 필터 연산을 즉시 중단(Break)하여 자원을 절약합니다.

## Alternatives Considered

### 1. SQLite EXPLAIN QUERY PLAN 활용
- Pros: DB 엔진 레벨의 가장 정확한 실행 비용 확인 가능.
- Cons: 1GB RAM 환경에서 파싱 오버헤드가 크고, SQLite의 EXPLAIN PLAN은 상대적 Cost 수치를 표준화하여 제공하지 않으므로 어플리케이션 계층에서의 정렬 기준으로 쓰기에 부적절함.
- Rejected: 휴리스틱 파라미터 연산이 압도적으로 가볍고 일관됨.

### 2. ThreadPool / Asyncio.gather 를 통한 병렬 실행
- Pros: 모든 필터를 동시에 던져 I/O 대기 시간을 최소화.
- Cons: 1GB RAM 환경에서 다중 윈도우 함수 쿼리가 동시에 SQLite Memory DB를 타격하면 Connection Pool 고갈 및 메모리 스파이크로 인한 OOM 발생 위험이 매우 큼.
- Rejected: 비용 기반 정렬 + Short-circuit 순차 처리가 훨씬 안전함.

## Consequences
- **극적인 성능 향상**: 벤치마크 테스트 결과, 60초 이상 걸리던 Heavy 분봉 탐색 시나리오들이 최대 16초~2초 대로 4배 이상 단축되며 타임아웃 병목이 해소되었습니다.
- 클라이언트(프론트엔드)는 기존 스펙(`filters`, `operations`)을 1바이트도 수정할 필요 없이 그대로 전송하면 백엔드가 알아서 최적화합니다.
- `run_pipeline_stream` (SSE 스트리밍) 환경에서도 재정렬된 순서대로 이벤트가 방출되므로 `FilterBlock` UI 렌더링에 부작용이 없습니다.
