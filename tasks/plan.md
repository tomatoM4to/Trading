# Implementation Plan: Live Status Admin API

## Components & Implementation Order
1. **Service Layer** (`app/services/admin_live_service.py`)
   - 목적: DB 연결(`conn`)을 주입받아 실제 SQLite `SELECT` 쿼리를 수행하고 결과를 반환.
   - 컴포넌트:
     - `get_global_status_service(data_type: str, conn: sqlite3.Connection)`
     - `get_ticker_status_service(ticker: str, data_type: str, conn: sqlite3.Connection)`
2. **Router Layer** (`app/routes/admin.py`)
   - 목적: `/admin/live` 접두사를 가지는 라우터를 추가하고 HTTP 요청을 받아 Service 레이어로 전달.
   - 컴포넌트:
     - `live_router` 인스턴스 생성 (`tags=["Admin (Live Status)"]`)
     - `@live_router.get("/global-status")`
     - `@live_router.get("/ticker-status/{ticker}")`

## Risks and Mitigations
- **DB Lock 위험**: `SELECT` 쿼리이므로 WAL 모드에서 Lock 유발 가능성은 낮으나, 데이터양이 큰 테이블에서 불필요한 Full-Scan을 막기 위해 쿼리를 간결하게 구성합니다.
- **SQL Injection 방지**: 파라미터 `data_type`은 Enum(또는 리스트 체크 `if data_type not in ('daily', 'minute')`)을 통해 사전에 차단합니다. `ticker`도 영숫자 정규식 체크 등으로 필터링할 수 있지만 내부 API이므로 SQL 파라미터 바인딩(`?`)을 사용하여 원천 차단합니다.

## Checkpoints
- Service 계층 작성 후, FastAPI Swagger UI(`http://127.0.0.1:8000/docs`)에서 직접 호출하며 포맷(JSON) 검증.
