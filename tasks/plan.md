# Plan: Test Endpoint Upgrade for In-Memory Sync Pipeline

## 1. Major Components & Dependencies
- `app/core/database.py`: `sync_memory_to_disk` 함수 리팩토링. (테스트 환경 라우팅 지원)
- `app/services/admin_test_service.py`: 일봉 및 분봉 테스트 로직 전면 개편. (In-Memory 구동 및 백업 파이프라인 검증 추가)

## 2. Implementation Order
1. **Component 1 (Database Refactor)**: `app/core/database.py`의 `sync_memory_to_disk(mem_conn=None)` 함수에 인자를 추가하여, 테스트용 메모리 커넥션을 외부에서 주입받을 수 있게 합니다. 또한 `test_db_var`가 존재할 경우 물리 디스크 경로를 강제로 `test_trading.db`로 라우팅하도록 안전장치를 추가합니다.
2. **Component 2 (Daily Test Upgrade)**: `app/services/admin_test_service.py`의 `test_daily_scheduler_integration_service`를 수정합니다.
   - 테스트용 `file:test_mem...` 인메모리 DB 생성 및 스키마 로드
   - 종목 3개 랜덤 추출 및 데이터 삭제(Slicing)로 갭(Gap) 생성
   - 백필(Backfill) 스케줄러 실행
   - `sync_memory_to_disk(test_mem_conn)` 호출
   - 디스크 파일(`test_trading.db`)에 직접 쿼리를 날려 데이터가 성공적으로 백업되었는지 2차 무결성 검증
3. **Component 3 (Minute Test Upgrade)**: 동일한 구조를 `test_minute_scheduler_integration_service`에도 적용합니다.

## 3. Risks & Mitigation
- **Risk**: 테스트 실행 시 인메모리 DB 이름 충돌로 인해 운영 DB 데이터와 섞일 가능성.
- **Mitigation**: 운영 환경의 `file::memory:?cache=shared` 대신 테스트 전용인 `file:test_daily_mem?mode=memory&cache=shared` 등 완전히 고유한 URI를 사용하여 물리적/논리적으로 완벽히 격리합니다.
- **Risk**: `sync_memory_to_disk`가 테스트 디스크 경로를 인식하지 못하고 라이브 DB에 덮어쓸 위험.
- **Mitigation**: `test_db_var.get()` 값을 최우선으로 리턴하는 방어 로직을 통해 근본적으로 차단합니다.

## 4. Parallelism
- Component 1을 먼저 수행한 뒤, Component 2와 3은 병렬적으로 작업할 수 있습니다.
