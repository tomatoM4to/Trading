# Implementation Plan: Minute OHLCV Scheduler

## Overview
KIS OpenAPI를 활용해 장중(09:00~15:55) 내내 거래 정지 종목(`is_halted=0`)을 제외한 전 종목의 1분봉 데이터를 실시간으로 무한 수집하는 백그라운드 스케줄러를 구축합니다. 
특히 서버 재시작이나 일시적 장애로 인해 발생하는 **데이터 공백(이빠진 부분)**을 완벽히 메우기 위해, `daily_scheduler`처럼 DB의 마지막 수집 시점(`last_time`)을 조회하고 최대 15번의 연속 호출(15-step backfill)을 통해 과거 분봉을 촘촘히 채우는 로직을 핵심으로 합니다.

## Architecture Decisions
- **쿼리단 필터링**: `SELECT ticker FROM stock_codes WHERE is_halted = 0`를 통해 불필요한 API 호출 방지.
- **연속 백필(Backfill) 로직 (Max 15 Steps)**: 종목별로 DB에 저장된 `last_time`을 확인한 뒤, 새로 Fetch한 데이터의 가장 오래된 시간이 `last_time`과 맞닿지 않으면 KIS API의 연속 조회(`tr_cont`) 기능을 이용해 최대 15회까지 과거로 거슬러 올라가 빈 공간을 채움.
- **순환 큐 & 1초 휴식**: 큐가 비워지면 1초 대기(`asyncio.sleep(1)`) 후 다시 큐를 채우는 방식의 무한 루프 구현.
- **안전한 스케줄링 전환**: 장 마감(15:30) 이후 지연 데이터를 고려해 15:55까지만 작동하게 하여, 16:00에 도는 일봉 스케줄러와의 DB Lock 및 API 한도 충돌을 원천 차단.
- **야간 가비지 컬렉션(GC)**: 분봉 데이터는 용량이 방대하므로 매일 밤 23:00에 최근 3일치만 남기고 과거 데이터를 삭제하는 쿼리 배치 실행.

## Task List

### Phase 1: Foundation (DB & Gap Analysis)
- [ ] Task 1: `minute_ohlcv` SQLite 테이블 스키마 생성 및 인덱스 최적화 (`ticker`, `date`, `time` 복합키)
- [ ] Task 2: 종목별 `MAX(date + time)`을 한 번에 가져오는 초기 상태 파악(Gap Analysis) 쿼리 작성

### Checkpoint: Foundation
- [ ] 스키마가 정상 생성되고, `MAX` 쿼리가 병목 없이 빠르게 리턴되는지 테스트

### Phase 2: Fetch & Backfill Logic
- [ ] Task 3: KIS 1분봉 API(`inquire_time_itemchartprice`) Fetch 함수 작성
- [ ] Task 4: `process_ticker` 내부에서 `last_time`과 비교하여, 끊긴 구간이 있으면 최대 15번(15-step) 연속 호출로 이빠진 데이터를 채우는 로직 구현

### Checkpoint: Fetch & Backfill
- [ ] 일부러 DB의 분봉을 몇 시간 치 삭제한 뒤, 스케줄러가 스스로 빈 구간을 인지하고 15-step backfill을 통해 꼼꼼하게 채워 넣는지 검증

### Phase 3: Core Loop & Time Bounds
- [ ] Task 5: 2,400개 종목을 큐에 넣고 소비하는 무한 루프 워커 구현 (1사이클 종료 후 1초 휴식)
- [ ] Task 6: 장중(09:00~15:55) 작동 시간 제한 로직 적용

### Phase 4: Integration & GC
- [ ] Task 7: `app/core/scheduler.py`에 분봉 스케줄러 태스크 등록
- [ ] Task 8: 야간(23:00) 낡은 데이터 삭제(GC) 스케줄 추가

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 이빠진 구간 백필(Backfill) 시 연속 호출로 인한 Rate Limit 폭발 | High | 기존에 구축된 `async_kis_fetch`의 PriorityQueue(초당 20회 제어)를 그대로 경유하여 안전하게 처리 |
| DB Lock (Database is locked) 에러 | High | WAL 모드 활용 및 Bulk UPSERT 처리, 그리고 일봉/분봉 스케줄러 시간 완전 분리(15:55 vs 16:00) |
| 장기 운용 시 SQLite 용량 폭발 | High | 야간 GC 스케줄러를 통해 지정일 이상 된 데이터 무조건 삭제 |

## Open Questions
- 분봉 데이터를 며칠치 보관하는 것이 스크리너 전략(예: 분봉 기반 200선 = 200분)에 가장 적합할까요? (현재 임시로 3일치 보관으로 계획)
