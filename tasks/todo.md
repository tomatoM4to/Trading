## Task 1: 종목 마스터 심화 필터링 및 컬럼 다이어트 구현

**Description:** `init_stock_codes.py`의 KOSPI 및 KOSDAQ 파싱 로직에 단기과열종목, 저유동성종목, 투자주의환기종목(코스닥)을 배제하는 필터링을 추가합니다. 또한 SQLite DB 저장 전, 조인으로 대체 가능한 `prev_vol`과 트레이딩에 불필요한 `capital` 컬럼을 제거하여 저장 용량과 메모리를 최적화합니다.

**Acceptance criteria:**
- [x] 코스피 종목 필터링에 `단기과열 == "0"` 및 `저유동성 != "Y"` 조건이 추가됨.
- [x] 코스닥 종목 필터링에 `단기과열종목구분코드 == "0"`, `저유동성종목 여부 != "Y"`, `(코스닥)투자주의환기종목여부 != "Y"` 조건이 추가됨.
- [x] DB 저장 시 컬럼 딕셔너리(`kpi_cols`, `kdq_cols`)에서 `prev_vol`, `capital` 항목이 제거됨.

**Verification:**
- [x] Linter 통과: `uv run ruff check .`
- [x] Build/Run 통과: `uv run python -m app.tasks.init_stock_codes` (단독 실행)
- [x] Manual check: SQLite 접속 후 `PRAGMA table_info(stock_codes);` 쿼리로 제거된 컬럼 확인 및 전체 카운트(약 2400~2500개) 확인.

**Dependencies:** None

**Files likely touched:**
- `app/tasks/init_stock_codes.py`

**Estimated scope:** Small: 1-2 files

---

## Task 2: 중앙 집중형 스케줄러(SystemScheduler) 생성

**Description:** 1GB RAM 환경의 최적화를 위해 기존 싱글톤 패턴인 `AuthScheduler`를 리팩토링하여 범용적인 `SystemScheduler`로 탈바꿈합니다. 이 클래스는 단일 `AsyncIOScheduler`를 감싸며, 22:00에 인증 갱신 작업과 08:30에 종목 마스터 DB 초기화 작업을 모두 예약합니다.

**Acceptance criteria:**
- [x] `app/core/scheduler.py`에 `SystemScheduler` 클래스 구현.
- [x] 싱글톤 인스턴스 내에서 1개의 `AsyncIOScheduler`만 생성.
- [x] `start()` 호출 시 밤 10시 인증 갱신 Job과 매일 오전 8시 30분 `init_stock_codes_db()` 구동 Job이 각각 cron으로 예약됨.

**Verification:**
- [x] Linter 통과: `uv run ruff check .`
- [x] Manual check: 코드 리뷰를 통해 2개의 스케줄이 정상적인 cron trigger (hour/minute)를 사용하는지 확인.

**Dependencies:** Task 1

**Files likely touched:**
- `app/core/scheduler.py` (New)

**Estimated scope:** Small: 1-2 files

---

## Task 3: 스케줄러 앱 연동 및 레거시 제거

**Description:** FastAPI 앱의 생명주기(lifespan) 훅에서 기존에 사용하던 `AuthScheduler` 대신 새로 만든 `SystemScheduler`를 임포트하여 시작(`start()`)시키고 종료(`stop()`)시킵니다. 이후 쓸모없어진 `auth_scheduler.py` 파일을 레포지토리에서 완전히 삭제합니다.

**Acceptance criteria:**
- [x] `app/main.py`의 `lifespan` 훅 내에 `SystemScheduler().start()` 코드가 들어감.
- [x] 앱 셧다운 시 `SystemScheduler().stop()` 코드가 들어감.
- [x] 기존의 `auth_scheduler.py` 삭제됨.

**Verification:**
- [x] Linter 통과: `uv run ruff check .`
- [x] Build/Run 통과: `uv run fastapi dev app/main.py`
- [x] Manual check: FastAPI 서버가 정상 기동되며, 콘솔에 "Auth scheduler started" 대신 "System scheduler started"와 함께 서버가 0.0.0.0으로 바인딩되는지 확인.

**Dependencies:** Task 2

**Files likely touched:**
- `app/main.py`
- `app/tasks/auth_scheduler.py`

**Estimated scope:** Small: 1-2 files
