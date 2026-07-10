# Spec: Admin Router Refactoring (Daily Only)

## Objective
현재 `app/routes/admin.py` 파일은 약 600줄로 거대해졌으며, API 핸들러 내부에 데이터베이스 접근 및 검증 비즈니스 로직이 강하게 결합되어 있습니다. 이번 작업의 목표는 FastAPI Best Practices를 준수하여 **일봉(Daily) 관련 기능만** `app/services/admin_daily_service.py` 및 Pydantic 스키마 레이어로 리팩토링하는 것입니다. 분봉(Minute) 기능은 추후로 미룹니다.

## Assumptions
1. 이번 리팩토링 범위는 오직 `/admin/daily/check` 및 `/admin/daily/verify` 라우터 함수에 한정됩니다.
2. 기존 KIS API 호출 함수나 DB 테이블(`daily_ohlcv`, `stock_codes`) 스펙 자체는 변경하지 않습니다.
3. 응답 타입은 기존 `dict`에서 정의된 Pydantic 모델로 전환됩니다.

## Tech Stack
- Python >= 3.12
- FastAPI
- Pydantic v2
- SQLite

## Commands
- Lint & Format: `uv run ruff check . --fix` & `uv run ruff format .`
- Run Server: `uv run fastapi dev app/main.py`

## Project Structure
```
app/
 ├── routes/
 │    └── admin.py                 # 라우터, 엔드포인트 정의
 ├── services/
 │    └── admin_daily_service.py   # Daily 검증 비즈니스 로직 및 DB 조회
 └── schemas/
      └── admin.py                 # Pydantic 응답 스키마
```

## Code Style
```python
from pydantic import BaseModel
from typing import List, Dict, Any

class DailyCheckResponse(BaseModel):
    status: str
    target_total_tickers: int
    # ...

# service function
def check_daily_ohlcv_service(market: str) -> DailyCheckResponse:
    # DB logic here
    pass
```

## Testing Strategy
- 수동 API 테스트 (FastAPI Swagger UI를 통해 `/admin/daily/check` 및 `/admin/daily/verify` 검증)
- Ruff를 통한 정적 분석 및 린트 검사 (`uv run ruff check .`)

## Boundaries
- **Always do**: Pydantic 스키마를 통한 응답 검증. DB Connection의 확실한 회수 (`try...finally`).
- **Ask first**: Minute(분봉) 관련 코드 수정이 필요해질 경우. 기존 응답 JSON 구조를 하위 호환되지 않게 크게 변경할 경우.
- **Never do**: 기존의 유효한 데이터베이스 검증 로직 축소 및 누락.

## Success Criteria
- [ ] `/admin/daily/check` 엔드포인트가 정상 동작하며, Pydantic 모델로 응답함.
- [ ] `/admin/daily/verify` 엔드포인트가 정상 동작하며, Pydantic 모델로 응답함.
- [ ] `app/routes/admin.py` 내의 Daily 라우터 코드가 50줄 이내로 간결해짐.
- [ ] 린트(`ruff`) 통과.

## Open Questions
- 없음 (기존 응답 구조를 100% 반영하여 Pydantic 모델화 예정)
