# Spec: Live Status Admin API

## Objective
백그라운드 스케줄러가 라이브 운영 데이터베이스(`trading.db`)에 일봉 및 분봉 데이터를 정상적으로 수집/적재하고 있는지 한눈에 모니터링하기 위한 읽기 전용(Read-only) 관리자 API를 구축합니다. 
추후 프론트엔드 대시보드에서 활용될 예정이며, 수천 개의 전체 캔들 데이터 대신 요약된 메타 정보만 JSON 형태로 반환합니다.

## Tech Stack
- FastAPI
- SQLite3 (`app.core.database.get_db` 의존성 주입 활용)

## Commands
- **Dev**: `uv run fastapi dev app/main.py`
- **Lint**: `uv run ruff check . --fix`
- **Format**: `uv run ruff format .`

## Project Structure
- `app/routes/admin.py` → 기존 어드민 라우터 파일에 Prefix `/admin/live` 를 가지는 라우터 추가
- `app/services/admin_live_service.py` → 실제 라이브 SQLite 쿼리 로직 처리

## Code Style
```python
from fastapi import APIRouter, Depends, Query
from sqlite3 import Connection
from app.core.database import get_db

live_router = APIRouter(prefix="/admin/live", tags=["Admin (Live Status)"])

@router.get("/global-status")
def get_global_status(
    data_type: str = Query(..., description="'daily' 또는 'minute'"),
    conn: Connection = Depends(get_db)
):
    # 순수 읽기 전용 쿼리 실행
    # (예시) SELECT MAX(date) FROM daily_ohlcv
    pass
```

## Testing Strategy
- **수동 검증 (Manual Verification)**: 이 API는 라이브 환경의 `trading.db` 상태를 보여주는 것이 목적이므로, 모의 객체(Mock)를 쓰기보다는 로컬 환경에서 실제 DB 파일에 쿼리를 날려 예상된 JSON 포맷이 반환되는지 직접 점검합니다.
- 파괴적인 작업(INSERT/DELETE)이 전혀 없으므로 Test DB Routing (`test_db_var`)은 명시적으로 사용하지 않고, 기본값인 운영 DB 연결을 그대로 사용합니다.

## Boundaries
- **Always do**: 
  - 순수 읽기(`SELECT`) 쿼리만 사용하기.
  - 거래량이 없어 데이터 적재가 듬성듬성한 종목은 에러가 아닌 정상으로 응답 포맷에 포함하기.
  - 테이블 동적 선택 시 SQL Injection 방지를 위해 파라미터를 하드코딩된 리스트(`['daily', 'minute']`)로 엄격하게 검증하기.
- **Ask first**: 데이터베이스 스키마 추가/수정.
- **Never do**: 
  - 이 엔드포인트 내에서 `test_db_var` 컨텍스트를 세팅하여 테스트 DB로 우회하기 (라이브 DB를 봐야 하므로 절대 금지).
  - 2,400개 종목의 전체 시계열 원본 데이터를 한번에 가져와서 리턴하기 (메모리 폭발 방지).

## Success Criteria
1. **전역 검증 API (`/admin/live/global-status`)**:
   - `data_type=daily|minute` 파라미터를 받습니다.
   - 전체 테이블의 가장 최신 날짜(기준일)를 찾습니다.
   - 모든 종목을 순회하여, 최신 데이터가 기준일과 일치하지 않는 종목 목록과 전체 종목 중 최신화가 완료된 비율(%)을 반환합니다.
2. **개별 종목 검증 API (`/admin/live/ticker-status/{ticker}`)**:
   - `data_type=daily|minute` 파라미터와 `ticker` 값을 받습니다.
   - 해당 종목의 데이터 총 개수(Count), 첫 번째 적재 일자(First Date), 가장 마지막 적재 일자(Latest Date)를 JSON으로 반환합니다.

## Open Questions
- 전역 상태 API에서 최신 데이터가 일치하지 않는 종목 리스트가 너무 길어질 경우, 그냥 개수만 표기할지 배열로 모두 던져줄지 (현재는 둘 다 포함하는 것으로 설계하겠습니다).
