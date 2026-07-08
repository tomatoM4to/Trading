# 에이전트 규칙 (Agent Rules)

- **언어 설정**: 항상 한국어로 대답할 것. (Always speak in Korean)
- 사용자의 요청에 대해 친절하고 명확하게 답변하며, 코드 작성 및 수정 시 이 규칙을 준수할 것.

---

# 프로젝트 스펙 (Project Specifications)

## 1. 개요 (Overview)
- **프로젝트명**: Trading Server
- **목적**: 한국투자증권(KIS) OpenAPI를 활용한 자동 매매 및 시세/계좌 조회용 백엔드 서버 구축
- **주요 프레임워크**: FastAPI (Python 3.12+)
- **패키지 매니저**: `uv`

## 2. 주요 기능 및 아키텍처 (Key Features & Architecture)
- **FastAPI 백엔드 서버**:
  - `app/main.py` 를 진입점(entrypoint)으로 하는 REST API 서버.
  - 서버 구동 주기(lifespan)를 활용하여 백그라운드 작업을 관리함.
- **운영 환경 (Environment)**:
  - 모의투자(vps)는 고려하지 않으며, 오직 실전투자(PROD) 단일 모드로만 동작함.
- **자동 인증 토큰 관리 및 스케줄러 (Auth & Scheduler)**:
  - KIS API의 Rate Limit(1분당 1회 발급 제한)을 회피하기 위해 발급된 토큰을 프로젝트 외부(또는 루트)의 로컬 파일(`KISYYYYMMDD`)에 캐싱하여 재사용함.
  - `APScheduler`를 이용해 백그라운드에서 KIS API 토큰(OAuth)을 갱신하는 작업을 수행.
  - 서버 기동 시 파일 캐시를 확인하고, 만료되었거나 없을 시 즉시 발급. 이후 매일 밤 10시(22:00)에 새로운 토큰을 발급받아 유효성을 유지함.
- **글로벌 로깅 설정 (Global Logging)**:
  - `core.logging`을 통해 프로젝트 전역에 Rich 기반의 일관된 로거를 적용.
  - 진입점인 `app/main.py` 시작 시 `setup_logging()`을 호출하여 모든 하위 모듈이 동일한 로깅 규칙을 따르도록 관리함.
- **데이터베이스 연동 (Database)**:
  - SQLite를 기본 데이터베이스로 사용하며, 동시성 관리를 위해 WAL(Write-Ahead Logging) 저널 모드를 적용함.
  - 앱 시작 시점(`lifespan`)에 `init_sqlite_connection()`을 호출하여 DB 연결성을 사전에 검증함.
- **종목 유니버스 초기화 (Stock Universe Initialization)**:
  - 앱 기동 시 KIS 공식 스크립트를 통해 코스피/코스닥 마스터 파일을 다운로드 및 파싱함.
  - **데이터 정제**: 파생상품(ETF/ETN), 리츠, SPAC, 우선주 및 거래불가 종목(거래정지, 관리종목) 등을 완벽히 제거하여 '순수 매매용 보통주'만 남김.
  - **보존 및 적재**: 정량적 데이터(거래량, 시가총액 등)는 추후 쿼리 기반 동적 필터링을 위해 유지하며, CSV 백업(`app/data/`) 후 SQLite의 `stock_codes` 테이블로 덮어쓰기 저장함.
  - **테이블 스키마 (`stock_codes`)**:

    | 컬럼명 | 데이터/타입 | 설명 |
    |---|---|---|
    | `ticker` | 문자열 | 단축코드 (KIS API 주문/조회용) |
    | `name` | 문자열 | 종목명 (한글명) |
    | `market` | 문자열 | KOSPI / KOSDAQ |
    | `prev_vol` | 숫자형 | 전일거래량 |
    | `market_cap` | 숫자형 | 전일기준 시가총액 (단위: 억) |
    | `total_shares` | 숫자형 | 상장주수 (단위: 천 주) |
    | `capital` | 숫자형 | 자본금 |
    | `credit_able` | 문자열 | 신용주문 가능 여부 |
    | `margin_rate` | 숫자형 | 증거금비율 |
- **무지연(Zero-Latency) DB 전용 데이터 아키텍처**:
  - 사용자 요청 시 KIS API 통신으로 인한 병목을 원천 차단하기 위해, **모든 시세 및 지표 요청은 오직 내부 SQLite DB만을 조회**하여 응답하는 구조를 채택함.
  - `daily_ohlcv` (1일봉) 및 `minute_ohlcv` (1분봉) 테이블 스키마를 분리 운영하여, 장중 사용자 요청 시 일봉 과거 데이터와 당일 분봉 데이터를 실시간으로 병합(Aggregation)하여 응답 속도를 극대화함.
  - **테이블 스키마 (`daily_ohlcv`)**:
    | 컬럼명 | 데이터/타입 | 설명 |
    |---|---|---|
    | `ticker` | 문자열 (PK) | 단축코드 |
    | `date` | 문자열 (PK) | 영업일자 (YYYYMMDD) |
    | `open`, `high`, `low`, `close` | 숫자형 | 시가, 고가, 저가, 종가 |
    | `volume` | 숫자형 | 누적 거래량 |
    | `amount` | 숫자형 | 누적 거래대금 |
  - **테이블 스키마 (`minute_ohlcv`)**:
    | 컬럼명 | 데이터/타입 | 설명 |
    |---|---|---|
    | `ticker` | 문자열 (PK) | 단축코드 |
    | `date` | 문자열 (PK) | 영업일자 (YYYYMMDD) |
    | `time` | 문자열 (PK) | 체결시간 (HHMMSS) |
    | `open`, `high`, `low`, `close` | 숫자형 | 분봉 시/고/저/종가 |
    | `volume` | 숫자형 | 해당 분의 거래량 |
    | `amount` | 숫자형 | 해당 분의 거래대금 (누적대금 차분으로 정밀 역산) |
- **백그라운드 OHLCV 데이터 적재 스케줄러 (Daily & Minute)**:
  - `daily_ohlcv_scheduler.py` 및 `minute_ohlcv_scheduler.py`를 통해 전 종목 캔들 데이터를 비동기 큐를 활용해 수집.
  - **분봉(Minute) 정밀 제어 및 롤링 윈도우**: 120개 중 20분씩 겹치게(Overlap) 데이터를 요청하여 네트워크 유실을 완벽 방어하며, 누락 구간 없이 3.5일 치 초기 적재(Top-Down).
  - **분봉 거래대금(Amount) 정밀 역산 및 날짜 경계 버그 방어**: KIS API가 분봉별 거래대금을 제공하지 않아 누적거래대금(`acml_tr_pbmn`)의 차분(diff)으로 역산함. 이때 120개 캔들이 여러 날짜(Days)에 걸쳐있을 경우, 아침 09:00의 누적대금(작음)에서 전날 15:30의 누적대금(매우 큼)을 빼버려 거래대금이 마이너스(-)가 되는 치명적 수학 오류를 방지하기 위해, Pandas의 `where` 조건문을 사용하여 날짜가 같을 때만 차분을 인정하고 경계선은 종가×거래량 근사치로 안전하게 보정함.
  - **Pandas numpy 충돌 방지**: 커스텀 `DotDict` 래퍼로 인한 `__array_struct__` 에러를 방지하기 위해 순수 `dict` 캐스팅 후 DataFrame 변환 적용.
  - **무료 API 한계 극복 (Pure Retry Queue 전략)**: 내부 재시도(루프+sleep) 로직을 완전히 제거하고, API 접속 끊김 등 장애 발생 시 0.1초의 짧은 대기 후 해당 종목을 작업 큐(Queue)의 맨 뒤로 보내어 순환 재시도(최대 5회)하도록 설계함. 이를 통해 특정 종목 오류로 인한 파이프라인 병목을 방지하고 동적인 백오프(Backoff) 효과를 얻음.
  - **고속 덮어쓰기 (UPSERT)**: 중복 데이터 수집을 방어하고 수정주가 등 최신 정보를 업데이트하기 위해 `INSERT OR REPLACE` 기반 벌크 인서트 적용.
- **관리자 라우터 및 무결성 검증 (Admin & Test)**:
  - `app/routes/admin.py` 내부에서 `daily`와 `minute` 전용 서브 라우터를 분리하여 스케줄러 수동 제어 및 직관적인 API 문서화 제공.
  - `/admin/{daily|minute}/check`: 기준 마스터 테이블(`stock_codes`)과 쿼리를 결합하여 특정 시장(`market` 쿼리파라미터)의 데이터 정합성을 검증함. 일봉(Daily)의 경우 최신 데이터의 100% 갱신 여부와 과거 데이터(400일 이상) 보유율(90% 이상)을 듀얼로 검증하여 신규 상장 종목의 노이즈를 필터링함.
  - `/admin/{daily|minute}/verify`: 시스템 무결성을 증명하기 위한 무작위 표본 추출(Spot Check) 테스터. 5일~300일 전의 무작위 기간을 잡아 KIS API 실시간 응답과 내부 DB 데이터를 1:1로 초고속 비교 검증하여, 수정주가 갱신 누락 등을 완벽하게 잡아냄.
- **비동기 API 큐 및 동시성 제어 (Rate Limit 제어)**:
  - KIS API 호출 유량 제한을 수학적으로 완벽히 방어하기 위해 `kis_fetch.py`에 단일 워커(Single Worker) 큐 사용.
  - **0.15초 간격(150ms) 절대 보장**: 2026.04 최신 KIS 공식 가이드(동시 호출 시 100ms~150ms 텀 권장)를 반영하여 워커 대기 시간을 조절함으로써 `EGW00201` (초당 거래건수 초과) 및 L4 스위치 차단을 완벽히 방어함.
  - 앱 시작(`lifespan`) 시 `start_q_worker()`를 구동하고, 종료 시 `stop_q_worker()`로 안전하게 종료함.
- **자가 치유 (Self-Healing) DB 및 데이터 파이프라인**:
  - `trading.db` 파일이 삭제되거나 손상되어도 서버를 재기동하면 `init_sqlite_connection()`과 `init_stock_codes_db()`가 자동으로 스키마를 재생성하고 최신 종목 리스트를 복구함.
  - 이후 스케줄러 재구동 시 빈 테이블에 방대한 OHLCV 데이터가 알아서 롤링 적재되므로 완벽한 시스템 복원력을 자랑함.
- **API 응답 데이터 처리 (APIResp & DotDict)**:
  - 통신 결과는 `APIResp` 클래스로 래핑되며, 내부적으로 `DotDict`를 사용하여 중첩된 JSON 구조를 객체 속성(`body.output2[0].stck_clpr` 등)처럼 직관적으로 접근하도록 지원함.
  - Pandas DataFrame 변환에 최적화된 순수 `dict` 기반 구조를 채택함.
- **라우팅 및 TR_ID 관리 (Routing & TR_ID)**:
  - 각 KIS API의 엔드포인트 URL과 TR_ID는 전역 스키마(Enum)에 의존하지 않으며, 결합도를 낮추기 위해 `app/routes/` 하위의 개별 라우터 함수 내부에 지역 변수로 명시하여 관리함.
- **설정 파일 (Configuration)**:
  - `kis_devlp.yaml`: KIS API 앱키, 앱시크릿, 계좌번호 및 실전투자 통신 엔드포인트 URL(`prod`)을 관리.
- **MCP(Model Context Protocol) 연동**:
  - `kis-code-assistant-mcp` 디렉토리에 위치한 MCP 서버를 통해, KIS API 관련 코딩 어시스턴트 역할을 지원하는 확장 도구가 포함되어 있음.

## 3. 기술 스택 (Tech Stack)
- **언어**: Python >= 3.12
- **프레임워크**: FastAPI
- **주요 라이브러리**: `apscheduler`, `requests`, `pandas`, `uvicorn` 등
- **버전 관리 및 의존성**: `pyproject.toml`, `uv.lock`

## 4. 실행 방법 (Run & Debug)
- **디버그 모드 실행**: 프로젝트 진입점에서 아래 명령어를 통해 핫 리로드(Hot Reload)가 활성화된 디버그 모드로 서버를 구동할 수 있음.
  ```bash
  uv run fastapi dev app/main.py
  ```
