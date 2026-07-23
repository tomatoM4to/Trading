# Implementation Plan: Asynchronous Minute OHLCV Backfill

## Overview
현재 시스템은 서버 기동 시 정규장 시간(09:00~15:55)에만 분봉 스케줄러를 가동하며, 이 스케줄러가 '과거 데이터 백필(Backfill)'과 '실시간 수집'을 동시에 수행하는 구조입니다. 이로 인해 밤에 배포할 경우 다음 날 아침까지 백필이 지연되고, 장중에 배포할 경우 무거운 백필 작업이 실시간 수집 주기를 극도로 지연시키는 치명적인 문제가 발생합니다. 

이를 해결하기 위해 **'과거 데이터 백필'과 '실시간 폴링'을 완벽히 분리(Decoupling)**하여, 서버 기동 시 무조건 비동기로 백필을 수행하고, 실시간 스케줄러는 가볍게 최신 데이터만 가져오도록 아키텍처를 개선합니다.

## Architecture Decisions
- **Decoupled Schedulers**: 백필(최대 15-step)과 실시간 폴링(1-step)을 별도의 함수와 태스크로 분리합니다.
- **Limit Days (3일)**: OOM 방지 및 KIS API Rate Limit 절약을 위해 분봉 백필은 매매 전략(돌파)에 유의미한 최대 3영업일까지만 거슬러 올라가도록 제한합니다.
- **Fire-and-Forget Bootstrap**: `bootstrap.py`는 백필 태스크를 비동기로 던져두고(`create_task`) 바로 종료되어, 서버의 핵심 API(`/admin/live`)가 즉시 응답할 수 있도록 보장합니다.

## Task List

### Phase 1: Foundation (minute_ohlcv_scheduler.py Refactoring)
- [ ] Task 1: `process_ticker` 함수에 `limit_days` 및 `max_steps` 파라미터 추가하여 백필/실시간 모드 제어 기능 구현
- [ ] Task 2: 1회성 비동기 백필을 수행하는 `run_minute_backfill_task` (Queue Worker 패턴) 신규 작성
- [ ] Task 3: 기존 `run_minute_ohlcv_scheduler`가 `max_steps=1`로 가볍게 실시간(장중) 폴링만 담당하도록 최적화

### Checkpoint: Foundation
- [ ] `process_ticker`가 제한된 스텝과 일수만큼만 API를 호출하는지 확인
- [ ] 백필 큐와 실시간 큐가 문법 오류 없이 작성되었는지 확인

### Phase 2: Integration (bootstrap.py)
- [ ] Task 4: `bootstrap.py`에서 무조건 `asyncio.create_task(run_minute_backfill_task())`를 호출하도록 수정
- [ ] Task 5: 관리자 테스트(`admin_test_service.py`) 등 의존성 있는 코드들이 변경된 파라미터에 맞게 동작하도록 수정 (필요시)

### Checkpoint: Complete
- [ ] 야간 기동 시 백필 정상 동작 여부 확인
- [ ] 장중 기동 시 백필과 실시간 폴링이 동시에 락 없이 잘 동작하는지 논리 검증

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite Concurrent Write Lock | High | `process_ticker`가 트랜잭션을 1건씩 즉시 커밋(Commit)하고 닫으므로, 백필과 실시간 태스크가 동시에 실행되어도 SQLite WAL 모드 하에서 안전하게 처리됨 |
| KIS API Rate Limit (초당 20회) | Med | 50개의 Queue Worker를 유지하되, 내부적으로 0.05초 대기(Delay)가 KIS Fetcher에 있으므로 초과하지 않음 |
