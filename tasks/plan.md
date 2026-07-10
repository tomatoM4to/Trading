# Implementation Plan: OHLCV 데이터 무결성 검증 고도화 (Admin UI 연동 준비)

## Overview
기존의 단순 확인용 무결성 검증 라우터를 고도화하여, 향후 생성할 SQLAlchemy 기반 Admin 페이지(UI)에서 직관적으로 "이빨이 빠진 날짜(Missing Dates)"와 "값이 불일치하는 내역"을 렌더링할 수 있도록 JSON 응답 규격을 상세화합니다. 독립형 CLI 스크립트 대신 API 라우터를 단일 진실의 원천(SSOT)으로 사용합니다.

## Architecture Decisions
- **Gap Detection (누락 일자 추적)**: API가 100일 치 정상 캔들을 반환했으나 DB에 없는 경우, 단순 카운트만 올리던 것을 배열(`missing_dates: list[str]`)에 구체적인 날짜들을 Push하여 보관합니다. 휴장일은 API에서도 안 내려오므로 자연스럽게 순수 누락만 잡힙니다.
- **Admin UI Friendly JSON**: 반환되는 JSON은 나중에 React나 Next.js, 혹은 FastAPI Admin 템플릿에서 그대로 Table이나 Chart로 뿌릴 수 있도록 명확한 계층(Status, Summary, Mismatch Details, Missing Dates)을 갖게 구성합니다.

## Task List

### Phase 1: API Router 고도화
- [ ] Task 1: `app/routes/admin.py`의 `verify_daily_integrity` 로직에 `missing_dates` 추적 배열 추가.
- [ ] Task 2: 응답 JSON 규격에 `missing_dates` 필드 매핑 및 리턴 포맷 정돈.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| JSON 크기 비대화 | Low | Mismatch 샘플을 종목당 최대 5개로 제한한 기존 룰을 유지하여 방어 |
