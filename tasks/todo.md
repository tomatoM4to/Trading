- [ ] Task 1: In-Memory MA DB 커넥션 및 스키마 세팅
  - Acceptance: `core/database.py`에 `get_ma_db()` 커넥션 헬퍼가 추가되고, `daily_ma`, `minute_ma` (고정 6개 이평선 컬럼 포함) 생성 쿼리가 인메모리 DB에 적용된다.
  - Verify: 앱 부팅 시 인메모리 DB에 해당 테이블 2개가 정상적으로 잡히는지 `sqlite3` 콘솔이나 디버그 로그로 확인.
  - Files: `app/core/database.py`, `app/main.py`

- [ ] Task 2: Pure Python `MACalculator` 구현 및 테스트
  - Acceptance: `collections.deque` 기반으로 최신 200개 종가를 캐싱하고 O(1) 혹은 빠른 순수 파이썬 내장 연산으로 `ma5` ~ `ma200` 딕셔너리를 반환하는 클래스가 완성된다.
  - Verify: 간단한 목업(Mock) 종가 배열을 집어넣고 Pandas의 `.rolling(N).mean()` 결과와 동일한 값이 반환되는지 단위 테스트(pytest 또는 수동) 검증.
  - Files: `app/core/ma_calculator.py` (신규)

- [ ] Task 3: Bootstrapping 리빌드 파이프라인 구축
  - Acceptance: 서버 기동 시 또는 08:00 크론잡에서, 디스크 DB의 OHLCV를 `fetchmany()`로 읽어와 `MACalculator`를 초기화하고 인메모리 MA 테이블에 Bulk Insert하는 로직을 완성한다.
  - Verify: 더미 DB를 로드해 리빌드가 60초 이내에 완료되고 `minute_ma` 테이블에 결과가 채워지는지 로그 확인.
  - Files: `app/core/bootstrap.py`

- [ ] Task 4: Real-time Scheduler 연동
  - Acceptance: 기존 `daily_ohlcv_scheduler`, `minute_ohlcv_scheduler`가 새 캔들을 수집할 때, OHLCV는 디스크에 Insert하고 `MACalculator`를 거친 MA 결과는 인메모리 DB에 Insert하도록 역할을 분리한다.
  - Verify: 백그라운드 워커 1회 사이클을 돌려(테스트 모드) 디스크 DB와 인메모리 DB에 각각 올바른 값이 동시에 적재되는지 덤프 확인.
  - Files: `app/core/scheduler.py` 또는 워커 파일.

- [ ] Task 5: Screener 엔진 쿼리 전면 개편
  - Acceptance: 기존의 무거운 `WITH ... AVG() OVER()` 윈도우 함수를 모두 삭제하고, `SELECT * FROM minute_ma` 기반의 단순 비교(> , <) 쿼리로 교체한다. 390 캔들 초과 요청 시 에러를 반환하는 제한 로직을 추가한다.
  - Verify: API `/screener/run`에 기존 AST 필터를 던져 응답 속도가 O(1) (수 밀리초)로 나오는지 응답 시간 모니터링.
  - Files: `app/services/screener_service.py`, `app/routes/screener.py`
