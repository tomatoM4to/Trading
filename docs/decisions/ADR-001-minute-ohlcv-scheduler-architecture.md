# ADR-001: Minute OHLCV Scheduler Architecture

## Status
Accepted

## Date
2026-07-11

## Context
Zero-Latency 스크리너 API를 위해 장중(09:00~15:55) 1분봉 데이터를 전 종목(2,400여 개)에 걸쳐 지연 없이 수집하고 보관해야 합니다.
핵심 제약 조건:
- Oracle Cloud Free Tier 환경 (1 OCPU, 1GB RAM)으로 인해 Pandas Merge 연산 및 대규모 인메모리 처리 불가.
- KIS OpenAPI 호출 제한 (초당 20회) 방어 필요.
- 일시적인 네트워크 오류나 서버 재시작 시, 누락된 데이터(Gap)를 정확하게 메울 수 있어야 함.

## Decision
다음과 같은 아키텍처를 채택하여 분봉 파이프라인을 구축합니다.

1. **API 선정 (120-item Backward API)**:
   - 당일 데이터 30개만 제공하는 `주식당일분봉조회(FHKST03010200)` 대신, 과거 데이터를 120개씩 묶어서 제공하는 `주식일별분봉조회(FHKST03010230)`를 사용합니다.
2. **Gap Analysis 기반의 조기 종료 (Zero-Overhead)**:
   - 서버 기동 시 SQLite의 `MAX(date || time)`를 활용해 단 한 번의 쿼리로 모든 종목의 마지막 수집 시점(`last_datetime`)을 메모리 해시맵으로 가져옵니다.
   - 워커가 새로운 분봉을 수집할 때마다 반환된 분봉의 시간과 `last_datetime`을 비교하여, 겹치는 즉시 조기 종료(break)하고 메모리 해시맵을 최신화합니다.
3. **무한 루프 워커 (Infinite Queue Worker)**:
   - 50개의 비동기 워커가 무한 루프(`while True`) 속에서 2,400개 종목 큐를 비웁니다.
   - 큐가 모두 비면 1초 대기 후 재순환하며, 장 시간(09:00~15:55) 외에는 자체 대기 및 종료됩니다.
4. **가비지 컬렉터 (Nightly GC)**:
   - 1GB 스토리지 및 RAM 방어를 위해 매일 밤 23:00에 3일(72시간) 이상 지난 분봉 데이터는 `DELETE` 쿼리로 완전 삭제합니다.

## Alternatives Considered

### WebSockets (실시간 스트리밍)
- Pros: 실시간(Tick) 수준의 지연 없는 데이터 확보.
- Cons: 2,400개 종목을 구독할 경우 Connection 오버헤드와 이벤트 루프 병목이 발생하여 1GB RAM 환경에서는 OOM(Out Of Memory) 확정.
- Rejected: 리소스 한계로 인해 폴링(Polling) 기반 배치 작업으로 선회.

### Pandas-based In-memory Merging
- Pros: 데이터프레임 병합 및 결측치 처리가 쉬움.
- Cons: 매번 2,400개 종목의 DB 데이터를 Pandas로 로드하면 메모리가 초과됨.
- Rejected: SQLite 수준의 `INSERT OR REPLACE` 및 `window functions`로 연산 위임.

## Consequences
- KIS API 호출 횟수를 각 종목당 순환 주기별 단 1회로 억제하면서 완벽한 Backfill 무결성을 확보했습니다.
- SQLite에 데이터를 적재한 후 윈도우 함수를 통해 스크리너 로직을 DB 엔진단에서 처리할 수 있는 발판이 마련되었습니다.
- 단, 서버 시작 후 최초 Backfill 시에는 15-step 루프로 인해 종목당 최대 15회의 API가 소모될 수 있습니다. (전체 시스템 관점에서는 안전한 Trade-off)
