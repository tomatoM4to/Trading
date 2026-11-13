# 정합성 테스트 하네스

## Overview

목표는 기존 구현의 결함 검출이다. 운영 `app/`, `web/`, DB 스키마와 KIS 정책은 수정하지 않는다. 이전 테스트 기대값을 이식하지 않았으며 실제 스키마·수집기·Queue·SQL 필터·라우터를 실행한다. 확인된 실패는 `xfail`, skip 또는 완화한 기대값으로 숨기지 않는다. 기본 명령은 현재 **종료 코드 1**을 반환한다.

계획은 자산 조사 → 격리/계산 → 수집 → Queue → API/집계 → 복구/자원 측정 → 독립 검토 순으로 실행했다. 각 Stage는 이전 Stage의 통과를 요구하지 않는다.

### 교체 전 자산 조사와 처리

| 자산 | 역할과 한계 | 처리 |
|---|---|---|
| `tests/test_database_architecture.py` | 디스크 연결 및 MA 보존 일부 확인. 수집/전송 계약 없음 | 삭제 |
| `tests/test_market_chart.py` | 작은 메모리 DB에서 일봉 MA10 한 값 확인 | 삭제 |
| `tests/test_screener_logic.py` | 일부 SQL 경계와 MA 회귀. 메모리 주 DB 사용으로 디스크 ATTACH 차이 미검출 | 삭제 |
| `tests/test_regressions.py` | 보안 입력, Queue 재시작, 일부 쿼리. 전송·수집 전체 비교 없음 | 삭제 |
| 기존 고정 Fixture | 별도 원본 자료 없이 각 테스트 내부에서 임시 행/Mock 구성 | 재사용하지 않음 |
| `app/services/admin_test_service.py`, `admin_daily_service.py`, `admin_minute_service.py`와 `/admin/test/*` | 운영 DB 표본·실제 KIS·고정 테스트 파일 사용. 행 수/표본 비교로 완전한 정합성을 보장하지 못함. MA URI는 ContextVar로 분리되지 않음 | 공개 API 보존 제약에 따라 유지. 기본 하네스에서 실행하지 않음 |
| `test_db_var`, `test_mem_var`, 전역 Queue, MA keepalive | 운영 관리자 기능/수집 경로에서 사용하는 공용 자산 | 유지 |
| `scripts/benchmark_screener.py` | HTTP SSE 측정. `error` 또는 `complete` 없는 EOF도 Success가 될 수 있고 기대 종목 검증이 없음 | 오프라인·정답 비교를 선행하는 측정기로 교체 |
| `docs/benchmark-result/*.csv` | 과거 조건별 실험 기록 | 원문 보존 |

### 추적한 데이터 흐름

```text
main.lifespan → DB/MA 초기화 → Queue 시작 → 인증 → scheduler/bootstrap
daily/minute process_ticker → 요청 파라미터
  → async_kis_fetch → 전역 PriorityQueue(priority,counter)
  → 단일 consumer → to_thread(_do_fetch) → requests.get/post
  → APIResp/DotDict → 숫자·날짜 변환 → 디스크 UPSERT/commit
  → canonical OHLCV 순회 → MA 계산/메모리 교체
  → screener 비용 정렬·후보 축소·SQL → SSE
  → market SQL window → 차트 응답 → TS 분/주/월 집계
```

인증은 데이터 Queue와 별도 경계이고 HTTP timeout은 30초다. 데이터 요청 timeout은 10초이며 Queue consumer는 **전송 완료 후 0.1초** 대기한다. 시작 시각만 0.1초 차이라는 약한 기준으로 판정하지 않는다.

KIS Code Assistant MCP의 search/read_source_code로 [일봉 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_itemchartprice/inquire_daily_itemchartprice.py)와 [일별 분봉 공식 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_dailychartprice/inquire_time_dailychartprice.py)를 조회해 TR, 요청 필드, 100/120건 상한을 확인했다. 응답 Fixture는 실제 고객 데이터의 캡처가 아닌 합성 입력이다. 거래일 달력, 체결 누적값의 실제 증권사 특성까지 검증했다는 뜻은 아니다.

## Checkpoints

- 독립 기준: 고정 JSON의 전체 OHLCV 튜플, `Fraction`으로 계산한 각 MA 창, Python 목록/집합으로 계산한 필터와 AND 우선 OR 체인. 운영 함수의 출력을 기대값으로 재호출하지 않는다.
- MA의 기간 부족은 `None`, 저장 MA의 소수 둘째 자리 반올림은 독립 합계/분수 계산으로 확인한다. 차트 SQL MA는 반올림하지 않은 평균과 비교한다. 날짜·시간은 유효한 달력 날짜와 6자리 시각으로 구성한다.
- `tests/support.py`는 실제 KIS 설정을 읽기 전에 그 **정확한 경로만** 합성 설정으로 대체한다. `.env`나 토큰 캐시를 사용하지 않는다. 인증 단독 테스트의 `config_root`도 임시 경로다.
- HTTP Session 및 socket 외부 연결을 차단한다. Windows `asyncio` 내부 `socket._fallback_socketpair`의 자체 연결만 허용한다. 데이터 통합 테스트는 `requests.get/post`만 Fake로 교체하고 `_do_fetch`, Queue와 0.1초 대기는 실행한다. 전송 예산을 넘으면 Fake가 실패한다. Cold 테스트는 URL/TR/종목/조회 기간/플래그/timeout도 비교한다.
- 테스트별 임시 디스크 DB + UUID MA URI + 실제 `init_sqlite_connection()`을 사용한다. ContextVar뿐 아니라 환경 경로와 `_MA_MEM_DB_URI`, keepalive를 분리한다. 모든 Python `sqlite3.connect`와 SQL ATTACH 대상을 검사한다. 운영 MA URI 및 임시 루트 밖 DB는 거부한다.
- 디스크 연결의 URI 해석이 꺼진 Windows에서 ATTACH 문자열이 파일로 해석되는 것까지 검증하기 위해, 테스트 작업 디렉터리도 임시 폴더로 바꾼다. 결함을 숨기려고 운영 연결에 `uri=True`를 강제하지 않는다.
- 연결을 추적하고 종료 시 keepalive 이외 미종료 연결을 실패로 판정한 뒤 정리한다. ContextVar/환경/전역 URI를 복구한다. Queue를 종료하고 장애 재현 중 남은 태스크·전송 gate도 정리한다. 전역 패치와 cwd를 사용하므로 **동일 프로세스 병렬 테스트는 지원하지 않는다**.
- 차트 API는 실제 앱의 라우터/가드를 사용하지만 TestClient lifespan은 시작하지 않는다. 실제 시작은 인증과 스케줄러를 실행하기 때문이다. 프론트엔드 테스트는 사용자 요청으로 제거했으며 기본 하네스에는 Node/TypeScript가 필요하지 않다.

## Tests

### 설치와 기본 실행

```powershell
uv sync --locked
uv run --locked python -m tests.run
```

설치된 환경에서는 `.venv/Scripts/python.exe -m tests.run`으로도 실행할 수 있다. 이번 관리형 환경에서는 기본 uv 캐시 권한 때문에 임시 디렉터리의 별도 `--cache-dir`로 설치했다. `unittest discover -s tests -v`도 지원한다. 실행 지표는 `tests.run`이 콘솔에 출력하며, 필요할 때만 `--report <경로>`로 저장한다. 저장된 결과 JSON은 사용자 요청으로 제거했다.

```powershell
uv run --locked python -m tests.run --stage 1
uv run --locked python -m tests.run --stage 2
uv run --locked python -m tests.run --stage 3
uv run --locked python -m tests.run --stage 4
uv run --locked python -m tests.run --stage 5
uv run --locked python -m tests.run --stage 3 --match restart_does_not_overlap
uv run --locked ruff check tests scripts/benchmark_screener.py
uv run --locked ruff format --check tests scripts/benchmark_screener.py
```

| Stage | 독립 판정과 실패 경계 |
|---|---|
| 1 | 모든 MA 기간의 매 시점 값/부족 처리/종목·시간축 분리, MA 식별자 화이트리스트, STRICT PK/롤백, 디스크/MA/스레드 Context 격리, 위험 연결 차단 |
| 2 | 실제 Queue를 거친 cold/증분/중복/수정/과거 누락, 역순과 겹친 페이지, 빈/오류/잘못된 입력, 날짜 경계 누적값 초기화, DB 쓰기 실패와 재실행, 전체 OHLCV와 MA 보존·예열 비교 |
| 3 | 실제 전송 시작/완료 시각, FIFO/우선순위/직렬화, 취소, timeout 후 후속 요청, idle/in-flight 종료·재시작, 인증 실패·만료 캐시·재발급 |
| 4 | 모든 로컬 필터의 산술 참조, AND/OR 4조합과 순서 최적화 비교, 랭킹과 종목 자격, SSE 단일 terminal/오류, 차트 API 전체 OHLCV/시각/MA/일봉 overlay, 거래량 API |
| 5 | MA 메모리 소실 후 재구축, 별도 프로세스의 commit 직전/직후 강제 종료, 무결성 검사, WAL reader snapshot/checkpoint, 쓰기 잠금 실패·재시도, MA 실패·수집 취소·가드·GC |

`tests.run`은 테스트 수, 통과/실패/오류/스킵, 실패 ID, 시간과 peak RSS를 출력한다. 메서드 기준으로 집계해 여러 subTest 실패를 중복 합산하지 않는다. 상세 배열은 subTest를 포함한다. RSS는 **같은 Python 프로세스의 누적 최고치**이며 crash 자식과 OS page cache를 포함하지 않는다.

### 실제 KIS 선택 검증 — 이번 세션 미실행

```powershell
uv run --locked python -m tests.live_kis --allow-live --ticker 005930
```

기본 수집 대상에 포함하지 않는다. `--allow-live` 없으면 KIS 설정 import 전에 종료한다(거부 동작만 실제 확인). 범위는 **인증 발급 최대 1회 + Queue를 거친 일봉 읽기 최대 1회**, 최근 7일, 1종목으로 고정한다. 재시도·주문·계좌 조회·DB 쓰기가 없으며 로그와 오류 상세를 출력하지 않는다. 인증 함수는 기존 정책대로 토큰 캐시를 갱신할 수 있다. 자격 증명과 실제 응답의 수학적 정합성은 별도 승인된 검증에서 확인해야 한다.

### 성능 측정

[benchmark.md](benchmark.md)의 오프라인 명령으로 별도 실행한다. 64종목의 고정 데이터에서 32개 종목과 모든 필터 값을 비교한 뒤에만 성공/시간을 기록한다. 원격 HTTP·실제 KIS는 사용하지 않는다. 빈 결과나 미완료 SSE를 성공으로 판정하지 않는다.

## 실행 결과와 한계

2026-11-13, 소스 `5a363e6`, Windows / Python 3.12.12 / SQLite 3.50.4. 프론트엔드 3개를 제외한 백엔드 하네스 집계다. [결함 보고서](test-defects.md), [벤치마크 측정 조건과 요약](benchmark.md).

| Stage | 실행 | 통과 | 실패 | 오류 | 스킵 |
|---|---:|---:|---:|---:|---:|
| 1 | 5 | 5 | 0 | 0 | 0 |
| 2 | 14 | 9 | 5 | 0 | 0 |
| 3 | 7 | 4 | 3 | 0 | 0 |
| 4 | 7 | 3 | 3 | 1 | 0 |
| 5 | 10 | 7 | 3 | 0 | 0 |
| 합계 | 43 | 28 | 14 | 1 | 0 |

독립 검토자는 Windows ATTACH를 순수 SQLite로 재현했다. 차트 timestamp/일봉 overlay 누락과 전송 요청 종목 검증 누락도 지적했다. 둘 다 보강 후 원본 통과, 응답 MA 또는 요청 종목을 훼손한 mutation 실패를 확인했다. 테스트 검토 때문에 운영 코드를 수정하지 않았다.

| 미검증 영역 | 이유와 후속 검증 |
|---|---|
| 실제 KIS 원본/수정주가/장중 누적값 | 이번 요청에서 실제 호출을 허용하지 않음. 합성 Fixture 통과는 증권사 데이터 정합성 증거가 아님 |
| Linux ATTACH 동작 | Windows에서만 재현. Linux SQLite URI 기본 설정에 따라 달라질 수 있음 |
| 1 OCPU/1GB 제한과 OOM | Docker 엔진 권한/연결 없음. `docker info` 실패. 기존 이미지/의존성을 미리 준비한 환경에서 `--cpus=1 --memory=1g --network=none --read-only --tmpfs /tmp`로 재실행 필요 |
| 장시간 RSS 증가·2400종목 full load·heavy screener 중 health 지연 | 이번 측정은 64종목 단기 실행. 메모리 생존성/응답성 합격 기준을 수치로 임의 발명하지 않음 |
| 전체 lifespan, 예약시각, 인증 갱신과 수집의 장시간 공존 | 실제 인증/백그라운드 부작용이 있는 시작 흐름은 소스 추적에 그침. 개별 수명주기·가드/GC는 실행 |
| 마스터 다운로드/CSV→종목 변환 | 고정 app/data 출력 경로와 다운로드를 기본 하네스에서 실행하지 않음. 합성 마스터 원본을 이용한 후속 검증 필요 |
| 디스크 고갈/실제 I/O 손실/OS 강제 kill | trigger/잠금 및 `os._exit(23)`로 특정 중단점만 검증. 저장장치 장애를 재현한 것은 아님 |
| 프론트엔드 집계/브라우저 렌더링/SSE 사용자 취소 | 사용자 요청으로 프론트엔드 테스트를 제거. 이전 함수 단위 발견 내용 T16·T17은 과거 기록으로만 보존 |
| 관리자 검증 API 전체/실패 표본 집계 | 운영 자산을 건드리는 공개 검증 API는 조사만 수행. 기본 테스트 대체물로 사용하지 않음 |

운영 코드 변경 없이 해결한 환경 문제는 의존성 설치, 내부 socketpair 예외, 임시 cwd/DB/MA 라우팅, 인증 설정 주입이다. `unittest.assertRaises`의 traceback frame 정리가 Queue가 전달한 예외의 suspended consumer frame을 닫는 경우가 있어 전송 timeout은 명시적 try/except와 유한 대기로 관측한다. FastAPI의 잠금 의존성에서 TestClient deprecation 경고가 있지만 테스트 실행 오류는 아니다.

백엔드 후속 작업 우선순위는 Queue 종료·재시작 직렬화/미완료 Future/수집 worker 소유권 → 분봉 수정·거래대금·MA 실패 상태 → 스크리너 정렬/외부 오류·API schema → 플랫폼 ATTACH다. 각 수정은 해당 실패 테스트를 보존한 별도 작업으로 진행한다.
