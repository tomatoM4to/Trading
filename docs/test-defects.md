# 정합성·운영 안정성 결함 보고서

2026-11-13, 소스 `5a363e6`. 운영 코드는 수정하지 않았다. 재현 환경과 전체 집계는 [testing.md](testing.md)에 있다. T01–T15는 일반 실패/오류 테스트로 남아 있다. 프론트엔드 테스트와 저장된 결과 JSON은 사용자 요청으로 제거했으며 T16·T17은 과거 발견 기록으로 보존한다.

심각도 High는 데이터 왜곡·조회 장애·실패 은폐·실행 수명주기 위반, Medium은 조건부 입력/표시 오류 또는 불필요한 호출 소비로 분류했다. 고정 입력 또는 장애 주입으로 재현한 백엔드 결함 15건과 과거 프론트엔드 발견 2건을 기록한다. 실운영에서 같은 입력이 발생하는 빈도는 측정하지 않았다. 코드만 보고 높은 가능성으로 확정한 결함은 없다. Linux, 실제 KIS 응답 및 장시간 자원 제약은 별도 추가 검증 대상이다.

재현 명령 공통형은 다음과 같다. 각 항목의 Stage marker와 `-k`를 넣는다. 실패를 성공으로 바꾸지 않은 현재 코드에서는 종료 코드 1이 정상적인 결함 검출 결과다.

```powershell
uv run --locked pytest -m stage2 -k minute_latest_candle_revision
```

## T01 — 분봉 최신 캔들 수정 누락

- **High / 재현 완료. 위치:** `app/tasks/minute_ohlcv_scheduler.py:181`–190.
- **실제/기대:** DB 09:03 종가 120·거래량 4에 같은 timestamp의 121·5가 와도 기존 행 유지. 사용자 요구의 최신 캔들 UPSERT·수정 수집에 따라 신규 값과 MA에 반영돼야 한다.
- **최소 재현/실패 테스트:** Stage 2, `-k minute_latest_candle_revision`; 고정 4봉을 저장하고 마지막 봉을 수정한 응답과 `last_datetime=20261112090300` 전달.
- **원인/영향:** `dt_str > last_datetime`가 동시각 갱신을 제거하고 조기 종료한다. 장중 미완성 캔들의 OHLCV가 굳고 지표도 오래된 값으로 남을 수 있다.
- **권장 방향:** 겹친 캔들의 수정도 저장하고 그 canonical 구간에서 MA를 재계산한다. 호출량 증가는 별도 검증한다.

## T02 — 증분 분봉 거래대금 기준 행 제거

- **High / 재현 완료. 위치:** `app/tasks/minute_ohlcv_scheduler.py:186`, 203–213.
- **실제/기대:** 09:00 누적 100, 09:01 누적 311이면 다음 봉 대금은 **211**이어야 하지만 **220** 저장. Fixture의 open 101/close 110/volume 2에서 대금 211은 유효한 체결 합계이며 close×volume과 같을 이유가 없다.
- **최소 재현/실패 테스트:** Stage 2, `-k minute_increment_preserves_cumulative_baseline`; 09:00만 저장하고 09:03→09:00 응답을 증분 처리한다. 전체 튜플에서 09:01 amount가 다르다.
- **원인/영향:** 먼저 overlap을 제거해 차분에 필요한 이전 누적값을 잃은 뒤 끝 행을 종가×거래량으로 대체한다. 정확한 원본이 있는 상황에서도 거래대금을 왜곡한다.
- **권장 방향:** 차분에 필요한 경계 행을 유지한 상태로 정규화하고 이후 저장 범위를 결정한다. 기준값이 없는 페이지의 정확성 정책도 별도 정한다.

## T03 — 분봉 응답 행 순서에 따라 음수 대금 저장

- **Medium / 재현 완료(순서 내성), 실제 API 순서 보장은 추가 검증 필요. 위치:** `app/tasks/minute_ohlcv_scheduler.py:203`–213.
- **실제/기대:** 동일한 4봉을 시간 오름차순으로 주면 09:00 amount가 -211 등으로 저장된다. 이 작업의 정렬·역순 경계 검증 기준에서는 동일 시계열의 정규화 결과가 같거나, 지원하지 않는 순서를 명시적으로 거부해야 한다.
- **최소 재현/실패 테스트:** Stage 2, `-k minute_page_order_does_not_change_data`; 고정 원본 배열을 역전해 1페이지 처리한다.
- **원인/영향:** 정렬 없이 `shift(-1)`이 항상 이전 시점이라고 가정한다. 실제 KIS가 내림차순을 보장하는지/응답 순서가 바뀔 수 있는지는 미검증이며 정상 내림차순 Fixture는 통과한다.
- **권장 방향:** timestamp 순서를 검증·정렬한 뒤 날짜별 차분을 적용한다. API 명세의 보장 범위와 함께 결정한다.

## T04 — 잘못된 분봉 종가를 버린 뒤 수집 성공 반환

- **High / 재현 완료. 위치:** `app/tasks/minute_ohlcv_scheduler.py:198`, 217–219.
- **실제/기대:** 4봉 중 한 종가를 `bad-price`로 주면 3봉만 저장하고 `success=True`. 사용자 요구의 부분/잘못된 응답 구분에 따라 누락된 수집을 완전한 성공으로 보고하면 안 된다.
- **최소 재현/실패 테스트:** Stage 2, `-k minute_partial_bad_close_must_report_failure`; 나머지는 유효한 동일 고정 응답.
- **원인/영향:** `to_numeric(errors='coerce')`와 `dropna`로 문제 행을 제거하고 남은 행만으로 성공 판정한다. 재시도/갭 복구가 누락을 감지하지 못할 수 있다.
- **권장 방향:** 변환 실패를 명시적인 수집 실패 또는 불완전 상태로 전달한다. 조용한 누락을 허용하지 않는다.

## T05 — 최신 날짜가 있으면 앞 페이지 밖 과거 갭 미복구

- **High / 재현 완료. 위치:** `app/tasks/daily_ohlcv_scheduler.py:109`–113.
- **실제/기대:** 110일 중 내부 1일을 삭제하고 최신 날짜를 유지하면 최근 100일 응답에서 종료해 그 갭이 남는다. 사용자 요구의 과거 데이터 누락/Gap Recovery 기준에서 보존 범위 안의 알려진 누락은 복구돼야 한다.
- **최소 재현/실패 테스트:** Stage 2, `-k daily_internal_gap_before_overlap_page`; 0..109행 중 5번째만 제외하고 저장, 최근 100행과 그 이전 10행을 Fake에 준비한다.
- **원인/영향:** `MAX(date)`와 첫 overlap만으로 전체 역사 완전성을 추정한다. 최신 데이터가 있다는 사실은 과거 정합성을 보장하지 않는다.
- **권장 방향:** 복구 대상 기간의 누락을 별도로 식별한다. 임의 전량 재수집으로 호출량을 늘리지 말고 거래일 기준/수집 보존 계약을 먼저 정한다.

## T06 — Queue 대기 중 취소한 요청도 전송

- **Medium / 재현 완료. 위치:** `app/core/kis_fetch.py:160`–169, 286.
- **실제/기대:** 첫 요청을 gate로 막고 두 번째 대기 호출을 취소해도 두 번째가 HTTP로 나간다. 아직 전송하지 않은 작업의 취소는 호출량/대기열 비용을 해제해야 한다는 운영 기준으로 판정했다.
- **최소 재현/실패 테스트:** Stage 3, `-k cancelled_queued_request`; 실제 전송 label은 first/cancelled/last, 기대는 first/last.
- **원인/영향:** consumer는 완료/취소 Future를 전송 후에만 확인한다. HTTP 동작 자체의 오류는 아니지만 사용자 취소 후에도 호출 한도와 다른 요청의 시간을 소비한다.
- **권장 방향:** dequeue 후 이미 취소된 미전송 요청을 건너뛰고 Queue 완료 처리를 보장한다. 실행 중 HTTP 취소와 구분한다.

## T07 — Queue 종료 시 활성·대기 호출 Future가 미완료로 남음

- **High / 재현 완료. 위치:** `app/core/kis_fetch.py:196`–210.
- **실제/기대:** 활성 전송 1개와 대기 요청 1개가 있는 상태에서 stop 후 두 호출 모두 `done=False`. 종료된 Queue의 호출자는 취소/예외/결과 중 하나로 해제돼야 한다.
- **최소 재현/실패 테스트:** Stage 3, `-k stop_resolves_active_and_waiting`; transport gate와 응답 Future를 각각 관측한다.
- **원인/영향:** worker만 cancel하고 `_kis_queue=None`으로 버리며 payload Future를 resolve하지 않는다. 요청·작업 종료가 무기한 대기할 수 있다. 테스트는 관측 후 자체 취소로 정리한다.
- **권장 방향:** 활성/대기 Future의 소유권과 종료 정책을 명시하고 모든 대기를 해제한다.

## T08 — 전송 중 Queue 재시작 시 직렬화·0.1초 경계 위반

- **High / 재현 완료. 위치:** `app/core/kis_fetch.py:164`, 196–210.
- **실제/기대:** 첫 동기 전송이 끝나기 전에 새 worker가 두 번째 전송을 시작한다. 예시 실행에서는 두 번째 시작이 첫 번째 완료보다 약 0.15초 앞선다. 전송 직렬화와 완료 후 0.1초 정책을 재시작에서도 유지해야 한다.
- **최소 재현/실패 테스트:** Stage 3, `-k restart_does_not_overlap`; 첫 requests Fake를 gate로 막고 stop/start 후 두 번째 요청 제출.
- **원인/영향:** `to_thread`를 await하던 task의 취소는 실행 중인 스레드를 중단하지 않는다. worker 참조 초기화만으로 실제 전송의 종료를 보장할 수 없다.
- **권장 방향:** 진행 중 전송 완료와 대기 간격을 포함한 worker 종료/재시작 계약을 구현한다. 간격 축소로 해결하지 않는다.

## T09 — 비용 정렬로 거래정지 종목 포함 여부 변경

- **High / 재현 완료. 위치:** `app/services/screener_service.py:135`–157, 356–363, 807–827.
- **실제/기대:** MA→랭킹 순서에서 A만 나오지만 최적화가 랭킹을 먼저 실행하면 거래정지 H도 나온다. 사용자 요구와 `docs/screener.md`의 최적화 결과 불변 계약을 위반한다.
- **최소 재현/실패 테스트:** Stage 4, `-k cost_reordering_preserves_eligibility`; 정배열 A/H, H는 halted, 랭킹은 H/A. 동일 응답에서 비용 정렬만 끈 결과와 전체 값 비교.
- **원인/영향:** MA handler의 종목 자격 제한은 `current_tickers is None`에서만 적용된다. 랭킹 후보가 주어지면 해당 제한이 사라진다.
- **권장 방향:** 최적화 순서와 무관한 공통 종목 자격 계약을 적용하고 참조 결과를 유지한다.

## T10 — KIS 랭킹 실패를 정상 0건 SSE로 전달

- **High / 재현 완료. 위치:** `app/services/screener_service.py:805`, 252–255.
- **실제/기대:** HTTP 200이지만 KIS `rt_cd='1'`인 경우 `complete, items=[]` 반환. 외부 조회 실패는 정상 0건과 구분해 `error` terminal로 전달해야 한다.
- **최소 재현/실패 테스트:** Stage 4, `-k sse_broker_error`; 실제 POST `/api/screener/run`, Queue/HTTP Fake 사용.
- **원인/영향:** `_fetch_investor_rank`가 실패 시 빈 dict를 반환한다. 사용자는 외부 장애를 조건에 맞는 종목 없음으로 해석한다.
- **권장 방향:** 외부 실패를 명시적으로 전파하고 SSE generator가 실패 terminal을 생성하게 한다.

## T11 — 데이터가 있는 거래량 상위 API가 500 반환

- **High / 재현 완료. 위치:** `app/services/market_service.py:46`, `app/schemas/market.py:13`.
- **실제/기대:** `daily_ohlcv`가 비어 있지 않으면 `/market/screener/top-volume`이 500. 공개 응답은 날짜 문자열과 정확한 상위 종목·거래량이어야 한다.
- **최소 재현/실패 테스트:** Stage 4, `-k top_volume_nonempty`; 실제 STRICT INTEGER 날짜를 저장해 GET 호출.
- **원인/영향:** INTEGER `latest_date`를 Pydantic `date: str`로 직접 전달한다. 현 Pydantic 2.13.4는 자동 문자열 변환하지 않아 ValidationError. 빈 DB의 `N/A` 경로로는 검출되지 않는다.
- **권장 방향:** 공개 문자열 계약에 맞는 명시 변환을 적용한다. API schema 변경으로 회피하지 않는다.

## T12 — Windows 디스크 정본에서 MA URI ATTACH가 파일로 해석됨

- **High / 재현 완료(Windows), Linux 추가 검증 필요. 위치:** `app/core/database.py:49`, `app/services/screener_service.py:648`.
- **실제/기대:** 실제 MA 테이블이 존재해도 disparity 필터가 `no such table: madb.daily_ma` 또는 minute_ma 오류. 디스크 OHLCV와 Shared In-Memory MA를 연결해 산술 기준과 같아야 한다.
- **최소 재현/실패 테스트:** Stage 4, `-k disparity`; 일봉/분봉과 above/below의 4개 파라미터 사례가 SQLite 예외로 실패한다. 독립 검토자가 순수 sqlite3에서도 disk `uri=False`로 동일 증상, `uri=True`에서는 같은 MA 행 조회 성공을 확인했다.
- **원인/영향:** 해당 SQLite 빌드에서는 디스크 연결의 URI 해석이 꺼져 ATTACH의 `file:...`가 파일명으로 취급된다. Windows에서는 `file`과 ADS 형태 아티팩트가 생길 수 있다. 하네스는 임시 cwd에 격리한다.
- **권장 방향:** Linux 운영 빌드의 URI 설정도 확인한 후 명시적인 URI 연결 계약을 수립한다. 운영 DB 전체를 메모리로 바꿔 숨기지 않는다.

## T13 — MA 실패 후 수집 watermark로 재시도하면 MA 복구 건너뜀

- **High / 재현 완료. 위치:** `app/tasks/minute_ohlcv_scheduler.py:271`–284, 344–348.
- **실제/기대:** MA INSERT를 실패시키면 OHLCV는 저장되고 `(False,newest_dt)` 반환. trigger를 제거하고 같은 newest로 재시도해도 MA 0행. 재실행하면 canonical OHLCV에 해당하는 MA가 복원돼야 한다.
- **최소 재현/실패 테스트:** Stage 5, `-k minute_ma_failure_retry`; 실제 SQLite trigger로 MA 실패 주입 → 제거 → 재실행.
- **원인/영향:** 저장 실패 예외를 false로 바꾸지만 scheduler는 success를 무시하고 newest를 갱신한다. 이후 새 OHLCV가 없으면 `success_any=False`라 MA 재계산도 하지 않는다.
- **권장 방향:** OHLCV/MA 완료와 watermark 전진을 구분하고 실패한 MA 작업을 재시도 대상으로 남긴다.

## T14 — 부트스트랩 MA 실패가 호출자에게 성공처럼 반환

- **High / 재현 완료. 위치:** `app/core/bootstrap.py:134`–138.
- **실제/기대:** 실제 MA INSERT trigger가 실패해도 예외 없이 반환한다. 실패는 호출자와 준비 상태에 명시적으로 전달돼야 한다.
- **최소 재현/실패 테스트:** Stage 5, `-k bootstrap_rebuild_failure`; disk 5봉, daily_ma INSERT ABORT trigger, rebuild 호출.
- **원인/영향:** 예외를 로그만 남기고 삼키며 시스템 가드를 해제한다. 초기화가 불완전한 상태를 후속 단계/사용자가 준비 완료로 오인할 수 있다.
- **권장 방향:** 실패를 전파하거나 명시적인 실패 상태를 반환하고 준비 상태의 계약에 반영한다.

## T15 — 수집기 취소 후 하위 worker가 계속 살아 있음

- **High / 재현 완료. 위치:** `app/tasks/daily_ohlcv_scheduler.py:256`–263, `app/tasks/minute_ohlcv_scheduler.py:363`–366.
- **실제/기대:** 실제 수집기 부모를 Queue 대기 중 cancel하면 일봉 **100개**, 분봉 **50개** 하위 worker가 남는다. 취소된 수집기가 소유한 모든 하위 작업은 종료를 기다려야 한다.
- **최소 재현/실패 테스트:** Stage 5, `-k cancelled_collectors`; 한 종목의 Fake 전송을 막고 부모 취소, 새 live task 집합을 관측한다. 관측 후 하네스가 모두 정리한다.
- **원인/영향:** worker 취소가 정상 `queue.join()` 뒤에만 있으며 취소 시 finally 정리가 없다. 부모의 가드/진행 상태와 실제 쓰기 수명이 달라질 수 있다.
- **권장 방향:** 작업 소유권을 명시하고 정상·오류·취소 모두에서 cancel 및 await하는 구조를 적용한다.

## T16 — MA warmup 후 주봉 선의 timestamp가 캔들과 불일치 (과거 기록)

- **Medium / 재현 완료. 위치:** `web/lib/chart-utils.ts:168`–170, 211–214.
- **실제/기대:** 같은 주 월요일 MA null, 화요일 MA 102이면 주봉 캔들은 월요일, 선은 화요일 시각. 구현의 '캔들과 동일한 시간축' 계약에 따라 캔들 시각에 마지막 유효값 102가 붙어야 한다.
- **과거 재현:** 같은 주 월요일/화요일 입력으로 실제 TS를 Node에서 실행했다. 사용자 요청으로 자동 테스트를 제거했으며 현재 Stage 4에 포함되지 않는다.
- **원인/영향:** null 행을 그룹 계산 이전에 건너뛰어 첫 유효 MA 행을 그룹 기준 시각으로 선택한다. 선이 다른 캔들 위치에 그려질 수 있다.
- **권장 방향:** 값의 유효성과 캔들 그룹 기준 시각을 분리한다.

## T17 — 브라우저 시간대에 따라 주봉 OHLCV 집계 변경 (과거 기록)

- **Medium / 재현 완료. 위치:** `web/lib/chart-utils.ts:109`–113, 188–192.
- **실제/기대:** 2026-10-30, 11-02/03/09 KST 15:30 입력에서 서울 주봉 거래량은 `[1,5,4]`, LA 환경은 `[3,7]`. 동일 KST 시계열의 주간 경계는 사용자 브라우저 시간대와 무관해야 한다.
- **과거 재현:** 동일 TS·입력을 `TZ=Asia/Seoul`/`America/Los_Angeles` Node 프로세스에서 비교했다. 월봉 비교는 이 입력에서 통과했다. 사용자 요청으로 자동 테스트를 제거했으며 현재 Stage 4에 포함되지 않는다.
- **원인/영향:** KST 문자열로 생성한 Date에 로컬 `getDay/getDate/setDate`를 사용한다. LA에서 월요일이 일요일로 바뀌어 전주로 묶인다.
- **권장 방향:** 거래소 KST 달력 기준으로 일관된 그룹 키를 계산하고 캔들/선에서 공유한다.
