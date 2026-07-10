# Plan: Intelligent OHLCV Fetcher 구현

## 1. 컴포넌트 분석
- `app/tasks/daily_ohlcv_scheduler.py` 내부의 `process_ticker` 함수가 타겟입니다.
- 기존 로직: `target_api_calls = 5` 만큼 무조건 루프를 돔.
- 변경 로직: DB에서 해당 종목의 `MAX(date)`를 조회한 뒤 루프 종료 조건을 동적으로 제어.

## 2. 구현 순서 (Implementation Order)
1. **DB 조회 로직 추가**: `process_ticker` 시작 시점에 SQLite를 찔러 `SELECT MAX(date) FROM daily_ohlcv WHERE ticker = ?` 실행.
2. **분기점(Branch) 설계**:
   - `max_date`가 `None`인 경우 (신규): 기존처럼 `target_api_calls = 5` 유지.
   - `max_date`가 존재하는 경우 (기존):
     - `target_api_calls = 5` 로 최대치는 열어두되,
     - 한 번 API를 호출해서 받아온 캔들 리스트 중 `oldest_date <= max_date` 조건이 만족되면 **더 이상 과거로 갈 필요가 없으므로 `break`**.
3. **최적화**: DB 커넥션을 2,400번 새로 맺고 끊는 것은 비효율적이므로, 스케줄러 메인 함수(`run_daily_ohlcv_scheduler`)에서 미리 전 종목의 `MAX(date)`를 한 번에 딕셔너리로 조회(Map)하여 큐(Queue)에 담아 워커들에게 분배하는 방식이 압도적으로 빠름.

## 3. 리스크 및 완화 전략
- **리스크**: 상장폐지되거나 KIS API에서 아예 데이터가 응답되지 않는 깡통 종목 무한 루프.
- **완화**: 응답 데이터(`valid_items`)가 없으면 즉시 `break` 하는 기존 안전장치 유지.
