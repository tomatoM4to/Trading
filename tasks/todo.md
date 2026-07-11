# Minute OHLCV Scheduler Tasks

## Phase 1: Foundation (DB & Gap Analysis)
- [ ] Task 1: `minute_ohlcv` SQLite 테이블 스키마 생성 및 복합키(ticker, date, time) 세팅
- [ ] Task 2: 종목별 최근 수집 시점(`last_time`)을 한 번에 조회하는 초기화 로직 구현

## Phase 2: Fetch & Backfill Logic (15-Step Backfill)
- [ ] Task 3: KIS 1분봉 API(`inquire_time_itemchartprice`) Fetch 함수 작성
- [ ] Task 4: 수집된 분봉이 `last_time`과 맞닿지 않으면 최대 15회까지 연속 호출(`tr_cont`)하여 빈 구간을 완벽히 채우는 로직 구현

## Phase 3: Core Loop & Time Bounds
- [ ] Task 5: 2,400여 개 종목(`is_halted=0`) 큐 기반 무한 루프 구현 (1주기 종료 후 1초 대기)
- [ ] Task 6: 장중(09:00~15:55) 작동 시간 제한 로직 추가

## Phase 4: Integration & GC
- [ ] Task 7: `app/core/scheduler.py`에 분봉 스케줄러를 백그라운드 태스크로 추가
- [ ] Task 8: 야간(23:00) 낡은 데이터(3일 초과) 자동 삭제(GC) 스케줄 구현
