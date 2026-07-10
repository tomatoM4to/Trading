# Implementation Plan: Refactoring admin.py to Services (Daily Only)

## Overview
`app/routes/admin.py` 라우터 파일의 일봉(Daily) 관련 로직을 `/services` 레이어로 분리하고, Pydantic 모델을 `/schemas`에 정의하여 라우터의 책임을 최소화하고 응답 타입을 명확히 합니다.

## Architecture Decisions
- **Scope limitation**: 사용자의 요청에 따라 이번 작업은 **Daily(일봉)** 기능에만 집중합니다.
- **Service Layer (`app/services`)**: `admin_daily_service.py`를 생성하여 핵심 로직을 캡슐화합니다.
- **Schema Layer (`app/schemas`)**: `app/schemas/admin.py`에 `DailyCheckResponse`, `DailyVerifyResponse` 등의 모델을 정의합니다.

## Task List

### Phase 1: Foundation (Schema)
- [ ] Task 1: `app/schemas/admin.py` 생성 및 Daily 응답용 Pydantic 모델 정의

### Phase 2: Core Features (Service & Router)
- [ ] Task 2: `app/services/admin_daily_service.py` 생성 및 비즈니스 로직 이관
- [ ] Task 3: `app/routes/admin.py`의 Daily 라우터를 신규 Service 및 Schema로 연결

### Checkpoint: Complete
- [ ] `uv run ruff check .` 린트 에러 없음
- [ ] `/admin/daily/check` 및 `/admin/daily/verify` 정상 작동

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Circular Imports (순환 참조) | Medium | 함수 단위나 모듈 하단에서 import를 수행합니다. |
| DB Connection 누수 | High | Service 레이어 이전 시 `try-finally` 블록의 `conn.close()` 누락을 철저히 방지합니다. |
