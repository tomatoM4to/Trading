- [ ] Task: Service 계층 로직 구현 (`admin_live_service.py`)
  - Acceptance: `get_global_status_service`, `get_ticker_status_service` 함수가 쿼리를 잘 수행하여 Dictionary(JSON 변환 용이) 형태로 반환함.
  - Verify: Swagger UI 연동 후 육안 확인 (또는 테스트 라우터 작성 후 확인)
  - Files: `app/services/admin_live_service.py`

- [ ] Task: 라우터 연동 (`admin.py`)
  - Acceptance: `admin.py` 파일 내에 `live_router`가 추가되고 `get_db`를 Dependency로 사용하여 데이터를 Response 함.
  - Verify: `uv run fastapi dev app/main.py` 구동 후 `curl` 또는 Swagger UI 접속 시 정상 응답 반환.
  - Files: `app/routes/admin.py`
