# Implementation Plan: Minute OHLCV Scheduler Completion & Verification

## Overview
기존 코드베이스를 분석해본 결과, 분봉 스케줄러(`minute_ohlcv_scheduler.py`)의 핵심 로직(15-step 역추적, 거래대금 차분 계산 등)은 이미 90% 이상 훌륭하게 구현되어 있습니다. 하지만 **KOSDAQ 종목이 큐에 담기지 않는 버그**가 있고, 서버 부트스트랩 파이프라인 연동 및 통합 테스트 검증이 누락되어 있습니다. 이를 완벽하게 마무리(Complete)하는 작업을 진행합니다.

## Architecture Decisions
- **Unified Market Queue (시장 통합 큐)**: 현재 `run_minute_ohlcv_scheduler`가 무한 루프(while True)로 돌면서 `market="KOSPI"`만 처리하고 있어, KOSDAQ은 영원히 실행되지 못합니다. `market` 파라미터를 제거하거나 리스트로 받아, KOSPI와 KOSDAQ 전 종목(약 2400개)을 단일 `asyncio.Queue`에 담아 50개의 워커가 통합 처리하도록 수정합니다.
- **Bootstrap Pipeline 연동**: `app/core/bootstrap.py`에서 일봉 수집이 완전히 끝난 직후, 장중 시간(09:00~15:55)이라면 즉시 분봉 스케줄러가 비동기로(await 하지 않고 `create_task`) 띄워지도록 파이프라인을 연결합니다.
- **분봉 전용 통합 테스트 라우터**: 일봉에서 성공을 거둔 3단계 검증(콜드스타트 -> 삭제 후 복구 -> API 무결성 대조)을 분봉에도 똑같이 적용하여, `/admin/test/minute_scheduler` 엔드포인트에서 100% 무결성을 증명합니다.

## Task List

### Phase 1: Core Logic Completion (로직 완성)
- [ ] Task 1: `tasks/minute_ohlcv_scheduler.py`의 `run_minute_ohlcv_scheduler`가 KOSPI/KOSDAQ 종목을 모두 큐에 담아 처리하도록 개선
- [ ] Task 2: `core/bootstrap.py` 및 `core/scheduler.py`에서 분봉 스케줄러 기동 로직 연동

### Checkpoint: Core Logic
- [ ] 코드 문법 오류 없이 서버가 기동되며, `KOSPI`와 `KOSDAQ` 종목 개수가 합산되어 분봉 루프를 도는지 로깅 확인

### Phase 2: Integration Testing (무결성 증명)
- [ ] Task 3: `routes/admin.py`에 `GET /admin/test/minute_scheduler` 추가 (격리된 `test_trading.db` 사용)
- [ ] Task 4: 무작위 3종목에 대해 [콜드스타트 적재 -> 고의 슬라이싱 삭제 -> 스케줄러 재구동 -> KIS API 1:1 대조] 파이프라인 구현

### Checkpoint: Complete
- [ ] `/admin/test/minute_scheduler` 호출 시 3종목의 120개 캔들 데이터가 100% 완벽히 일치(Match)하는지 검증
- [ ] 운영 `trading.db`에 파괴적 영향이 없는지 재확인

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 09:00 캔들의 거래대금 차분 계산 오류 여부 검증 | High | Task 4의 무결성 테스트 시, API 원본의 09:00 거래대금과 DB에 적재된 09:00 거래대금이 일치하는지 집중적으로 Assert |
