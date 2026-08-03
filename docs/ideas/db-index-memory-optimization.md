# DB 다이어트 및 In-Memory 가속 아키텍처

## Problem Statement
"어떻게 하면 비대해진 중복 인덱스와 문자열 데이터 타입을 최적화하여 DB 용량을 최소화하고, 이를 인메모리(RAM)에 올려 스크리너 연산 시 치솟는 디스크 I/O 병목을 근본적으로 제거할 수 있을까?"

## Recommended Direction
**"초경량 스키마(Without ROWID) + In-Memory Replica 전략"**
1. **데이터 다이어트 & 타입 최적화**:
   - `date`, `time` 컬럼을 `INTEGER` 타입으로 변환하여 스토리지 용량 감소 및 비교 연산 속도 극대화.
   - `WITHOUT ROWID`, `STRICT` 도입으로 불필요한 자동 인덱스 생성을 막고 데이터 구조를 압축.
   - `idx_minute...` 등 3개의 무거운 명시적 중복 인덱스 전면 삭제.
2. **In-Memory 읽기 전용 복제본 (Read Replica)**:
   - 다이어트에 성공한 가벼운 DB(150~200MB 예상)를 FastAPI 부팅 시 SQLite의 `:memory:`로 복사.
   - 스크리너 엔진의 무거운 읽기(Read) 쿼리는 오직 메모리 DB에서만 수행하여 디스크 I/O를 0으로 수렴시킴.
3. **Pragma 극한 튜닝**:
   - 메모리 자원에 여유가 있으므로, `PRAGMA temp_store = MEMORY;`를 적용하여 윈도우 함수 연산 시 발생하는 임시 테이블 생성마저 디스크가 아닌 RAM에서 처리되도록 강제.

## Key Assumptions to Validate
- [ ] **메모리 안정성 한계치**: In-Memory DB 세팅과 `temp_store=MEMORY`를 동시에 가동한 상태에서, 동시다발적인 스크리너 교집합 연산 수행 시 1GB RAM 머신에서 OOM(Out of Memory)이 발생하지 않는가?
- [ ] **PK Backward Scan 작동 여부**: 별도의 내림차순(`DESC`) 전용 인덱스 없이, 기본 PK B-Tree 만으로 SQLite 옵티마이저가 윈도우 함수의 `ORDER BY date DESC, time DESC` 정렬을 풀스캔 없이 역방향으로 깔끔하게 처리해내는가? (`EXPLAIN QUERY PLAN` 확인)
- [ ] **데이터 정합성 (Master-Replica Sync)**: 디스크 DB(Master)에 최신 분봉 시세가 계속 쓰여질 때(Write), 락(Lock) 없이 메모리 DB로 데이터를 실시간 동기화시킬 파이프라인을 어떻게 구성할 것인가?

## MVP Scope (우선 구현 범위)
1. `database.py` 스키마 엎기 (`INTEGER` 타입화, `WITHOUT ROWID`, `STRICT` 적용, 쓸데없는 인덱스 삭제).
2. FastAPI 엔진 기동 시 임시 `:memory:` DB 커넥션을 뚫고 기존 디스크 데이터를 밀어넣는(Backup) 테스트 로직 구현.
3. 스크리너 쿼리에 `temp_store=MEMORY` 주입 후 디스크 I/O 모니터링.

## Not Doing (and Why)
- **DuckDB 등 타 분석용 DB 엔진 도입**: 기존에 공들여 짜놓은 SQLite 윈도우 함수 SQL과 아키텍처를 전면 재작성해야 하는 비용이 기회비용보다 훨씬 크기 때문.
- **Covering Index 추가**: 쿼리 속도는 약간 빨라지겠지만 인덱스 용량이 팽창하여 "DB를 통째로 메모리에 올린다"는 핵심 전략과 정면으로 충돌함.
- **장기 분봉 데이터 보존**: 메모리 용량 사수를 위해 분봉 데이터는 철저하게 최근 7일치(또는 지정된 임계치)만 유지하도록 GC 정책을 더 공격적으로 적용.

## Open Questions (남은 고민)
- **변환 레이어 위치**: 문자열(TEXT) 형태의 날짜/시간을 프론트엔드와 주고받을 텐데, DB용 정수형(`INTEGER`)으로 변환(Parsing/Formatting)하는 레이어를 FastAPI 라우터 단에 둘 것인가, 아니면 SQL DTO 객체 단에 둘 것인가?
