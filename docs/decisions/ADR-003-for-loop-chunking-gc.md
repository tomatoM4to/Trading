# ADR-003: For-Loop Chunking Strategy for Garbage Collection

## Status
Superseded by ADR-015

## Date
2026-07-12

## Context
1GB RAM, 오라클 클라우드 프리티어 환경에서 무한정 쌓이는 시계열 데이터(일봉, 분봉)를 통제하기 위해 매일 23시에 가비지 컬렉터(GC)를 실행해야 합니다. 
요구사항은 "일봉은 종목별로 최신 500개(영업일 500일치), 분봉은 종목별로 최신 1560개(영업일 4일치)만 남기고 삭제"하는 것입니다.

## Decision
단일 거대 SQL 쿼리(Correlated Subquery) 대신, 파이썬 단에서 **For-Loop Chunking** 방식을 도입하여 종목별로 개별 삭제 쿼리를 실행합니다.

1. **종목별 청크 분할 (Chunking)**
   - `stock_codes` 테이블에서 2,400개 종목을 먼저 조회한 후, `for ticker in tickers:` 루프를 돕니다.
2. **Offset 활용 삭제**
   - 각 종목별로 `ORDER BY date DESC LIMIT 1 OFFSET 499` (분봉은 1559) 쿼리를 통해 커트라인 날짜/시간을 O(1)에 가깝게 찾아냅니다 (PK 인덱스 활용).
   - 이후 찾아낸 날짜 이전의 데이터를 `DELETE` 합니다.
3. **종목 단위 트랜잭션 릴리즈**
   - 종목 하나의 일봉/분봉 삭제가 끝날 때마다 즉시 `conn.commit()`을 수행합니다.

## Alternatives Considered
- **단일 `DELETE` 쿼리와 서브쿼리 사용**:
  - Pros: 쿼리 한 줄로 파이썬 코드가 간결해짐.
  - Cons: 수백만 건의 데이터를 종목별로 파티셔닝하여 삭제하려면 대규모 Sort와 락(Lock)이 수반되어 SQLite 및 1GB RAM 환경에서는 OOM이나 `database is locked` 에러를 유발할 확률이 100%에 수렴.
  - Rejected: 무인 자동화 서버의 안정성이 최우선이므로 기각.
- **`VACUUM` 명령어를 통한 물리적 용량 축소**:
  - Pros: `.db` 파일 크기가 즉시 줄어듦.
  - Cons: SQLite에서 `VACUUM`은 DB 전체를 복사하므로 임시로 2배의 용량이 필요하고, 실행되는 동안 DB가 완전히 락아웃 됨.
  - Rejected: 파일 크기가 무한정 커지지 않고 남은 빈 페이지(Empty Pages)를 재활용(Reuse)하는 SQLite의 기본 메커니즘에 의존하는 것이 락오버헤드 방지 차원에서 더 유리하다고 판단.

## Consequences
- 전체 DB가 장시간 Lock되는 현상을 원천 차단하여 야간 유지보 작업의 안정성이 확보되었습니다.
- 단일 쿼리보다 전체 수행 시간은 다소 길어질 수 있으나, 심야 시간(23:00) 백그라운드 스케줄러에서 동작하므로 트레이딩과 데이터 수집에 아무런 영향을 주지 않습니다.
- 물리적 파일 크기는 삭제 직후 줄어들지 않으나, 새로 유입되는 데이터가 해당 빈 공간을 재사용하므로 일정 크기(Plateau)에서 스토리지 점유율이 멈추게 됩니다.
