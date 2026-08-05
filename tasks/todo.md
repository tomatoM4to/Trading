# Tasks: Test Endpoint Upgrade for In-Memory Sync Pipeline

- [ ] **Task 1: `sync_memory_to_disk` 방어 로직 및 의존성 주입 리팩토링**
  - **Acceptance**: 인자로 `mem_conn: sqlite3.Connection | None = None`을 받도록 수정하고, `test_db_var`가 있을 경우 디스크 경로를 오버라이드한다.
  - **Verify**: 코드 리뷰를 통해 디스크 덮어쓰기 취약점이 완전히 사라졌는지 확인한다.
  - **Files**: `app/core/database.py`

- [ ] **Task 2: 일봉 통합 테스트 (`test_daily_scheduler_integration_service`) 개편**
  - **Acceptance**: In-Memory 기반으로 구동되며, 데이터 Slicing -> Backfill -> `sync_memory_to_disk(mem_conn)` -> 물리 디스크(`test_trading.db`) 데이터 검증 순서로 100% 통과한다.
  - **Verify**: API를 호출하여 `{ "status": "success" }`와 무결성 검증 메시지를 확인한다.
  - **Files**: `app/services/admin_test_service.py`

- [ ] **Task 3: 분봉 통합 테스트 (`test_minute_scheduler_integration_service`) 개편**
  - **Acceptance**: 일봉과 동일하게 In-Memory 기반 구동 및 디스크 백업 무결성을 검증하는 구조로 리팩토링한다.
  - **Verify**: API를 호출하여 `{ "status": "success" }`를 확인한다.
  - **Files**: `app/services/admin_test_service.py`
