## Task 1: Create Pydantic models for Daily Endpoints

**Description:** `/admin/daily/check` 및 `/admin/daily/verify` 라우터의 반환 값을 정의하는 Pydantic `BaseModel` 기반 응답 스키마를 `app/schemas/admin.py`에 구현합니다. 기존 딕셔너리 구조를 철저히 매핑합니다.

**Acceptance criteria:**
- [x] `app/schemas/admin.py` 파일 생성
- [x] `DailyCheckResponse` 및 `DailyVerifyResponse` 등 스키마 정의

**Verification:**
- [x] 구문 에러 없음 확인

**Dependencies:** None

**Files likely touched:**
- `app/schemas/admin.py`

**Estimated scope:** Small: 1 file

---

## Task 2: Create Daily Admin Service

**Description:** `admin.py`의 `check_daily_ohlcv` 및 `verify_daily_integrity`에 있는 DB 접근 및 KIS API 호출 비즈니스 로직을 `app/services/admin_daily_service.py`로 분리합니다.

**Acceptance criteria:**
- [x] `app/services/admin_daily_service.py` 파일 생성
- [x] `check_daily_ohlcv_service(market: str) -> DailyCheckResponse` 구현
- [x] 비동기 `verify_daily_integrity_service(sample_size: int, market: str) -> DailyVerifyResponse` 구현

**Verification:**
- [x] Linter 통과

**Dependencies:** Task 1

**Files likely touched:**
- `app/services/admin_daily_service.py`

**Estimated scope:** Medium: 1 file

---

## Task 3: Update Daily Routes

**Description:** `app/routes/admin.py` 내부의 Daily 라우터가 새로 생성된 서비스 함수를 호출하도록 단순화하고, 정의된 Pydantic 모델을 응답 타입으로 지정합니다.

**Acceptance criteria:**
- [ ] `check_daily_ohlcv`와 `verify_daily_integrity` 라우터 내부 로직이 제거되고 서비스 호출로 대체됨
- [ ] 라우터 데코레이터에 `response_model` 적용

**Verification:**
- [ ] `uv run ruff check .` 통과
- [ ] 서버를 실행하여 `/admin/daily/check` 호출 시 에러 없음

**Dependencies:** Task 1, Task 2

**Files likely touched:**
- `app/routes/admin.py`

**Estimated scope:** Small: 1 file
