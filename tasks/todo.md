## Task 1: 분봉 스케줄러 시장 통합(Unified Queue) 처리

**Description:** `tasks/minute_ohlcv_scheduler.py` 내의 메인 함수들이 단일 `market` 파라미터에 얽매이지 않고, KOSPI와 KOSDAQ 전 종목을 데이터베이스에서 한 번에 긁어와 단일 큐(Queue)에 담아 병렬 처리하도록 로직을 수정합니다.

**Acceptance criteria:**
- [ ] `run_minute_ohlcv_scheduler` 함수가 `market`을 파라미터로 받지 않거나 (혹은 기본값 `None` 처리), DB에서 KOSPI와 KOSDAQ 종목을 모두(`WHERE is_halted=0`) 조회한다.
- [ ] 무한 루프 내에서 약 2,400개 전 종목이 하나의 `queue`에 담겨 워커들에 의해 분산 처리된다.

**Dependencies:** None

**Files likely touched:**
- `app/tasks/minute_ohlcv_scheduler.py`
- `app/core/scheduler.py`

**Estimated scope:** Small: 2 files

---

## Task 2: 부트스트랩 파이프라인(Bootstrap) 연동

**Description:** 서버가 기동될 때 실행되는 `core/bootstrap.py` 파이프라인에서, 마스터 데이터 및 일봉 적재가 모두 끝난 뒤 장중(09:00~15:55)이라면 분봉 스케줄러가 알아서 시작되도록 연동합니다.

**Acceptance criteria:**
- [ ] `app/core/bootstrap.py` 마지막 단계에 `start_minute_scheduler_task()` 호출이 추가된다.
- [ ] 09:00~15:55 사이라면 백그라운드 태스크로 분봉 수집이 정상적으로 시작된다.

**Dependencies:** Task 1

**Files likely touched:**
- `app/core/bootstrap.py`

**Estimated scope:** Small: 1 file

---

## Task 3: 관리자용 분봉 통합 테스트 라우터 구현

**Description:** 일봉 테스트와 유사하게 `/admin/test/minute_scheduler` 엔드포인트를 만들어, `test_trading.db` 환경에서 무작위 3종목의 분봉 데이터를 콜드스타트 적재하고 강제 삭제 후 다시 복구시키는 시나리오를 구현합니다.

**Acceptance criteria:**
- [ ] `routes/admin.py` (또는 `test_router`)에 `GET /admin/test/minute_scheduler` 가 생성된다.
- [ ] `contextvars`를 통해 `test_trading.db`로 연결을 전환하고, 무작위 3종목을 세팅한다.
- [ ] 분봉 스케줄러를 딱 1 Cycle(무한 루프 제거 버전 또는 break 조건 삽입)만 돌려서 3종목의 분봉이 정상 적재되는지 확인한다.
- [ ] 3종목의 최근 30개 분봉 캔들을 강제 `DELETE` 하고 다시 1 Cycle을 돌려 원래 캔들 개수로 복구되는지 검증한다.

**Dependencies:** Task 2

**Files likely touched:**
- `app/routes/admin.py`
- `app/tasks/minute_ohlcv_scheduler.py` (테스트용 단일 사이클 플래그 `single_cycle=False` 추가 등)

**Estimated scope:** Medium: 2 files

---

## Task 4: API 실시간 데이터 1:1 무결성 대조

**Description:** Task 3에서 복구가 완료된 분봉 데이터를 KIS API에서 한 번 더 긁어와서, 최근 120개 분봉의 가격과 거래대금이 DB와 100% 완벽히 일치하는지 마지막으로 확인합니다.

**Acceptance criteria:**
- [ ] 기존에 만들어둔 `verify_minute_integrity` 내부 로직을 재사용하여 API 응답과 DB를 비교한다.
- [ ] Mismatch가 0건인지 검증하여 응답 JSON에 반환한다.
- [ ] 특히 09:00:00 시점 캔들의 거래대금이 차분 누락 없이 API 원본 그대로 잘 적재되었는지 중점적으로 테스트된다.

**Dependencies:** Task 3

**Files likely touched:**
- `app/routes/admin.py`

**Estimated scope:** Medium: 1 file
