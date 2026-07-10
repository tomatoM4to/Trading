## Task 1: 스케줄러 워커에 MAX(date) 딕셔너리 주입 로직 구현

**Description:** 일봉 스케줄러 메인 루프 시작 전, `daily_ohlcv` 테이블에서 전 종목의 `MAX(date)`를 한 번에 GROUP BY로 가져와 메모리 딕셔너리에 올리고, 이를 비동기 큐 아이템에 포함시킵니다.

**Acceptance criteria:**
- [x] `run_daily_ohlcv_scheduler`에서 `SELECT ticker, MAX(date) FROM daily_ohlcv GROUP BY ticker` 쿼리 실행.
- [x] 결과를 딕셔너리로 변환하여 큐 아이템에 `{"ticker": "005930", "last_date": "20260705", ...}` 형태로 삽입.

**Verification:**
- [x] Linter 통과 (ruff).

---

## Task 2: process_ticker 지능형 중단(Break) 로직 구현

**Description:** `process_ticker`가 `last_date` 파라미터를 받아, API 응답의 가장 오래된 날짜가 `last_date`보다 작거나 같아지면 불필요한 과거 조회를 멈추도록(Break) 루프를 최적화합니다.

**Acceptance criteria:**
- [x] `process_ticker(ticker: str, last_date: str = None)` 서명 변경.
- [x] 루프 내에서 가져온 `valid_items`의 최소 날짜(`oldest_date_str`)를 추출.
- [x] `last_date`가 존재하고 `oldest_date_str <= last_date` 이면 루프 즉시 `break`.

**Verification:**
- [x] Linter 통과 (ruff).
- [x] 관리자 라우터(`/admin/daily/start`)를 통해 수동 구동 후 콘솔 로그에서 대부분 1회 호출로 종료되는지 확인.
