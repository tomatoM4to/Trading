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
- **설정 파일 (Configuration)**:
  - `kis_devlp.yaml`: KIS API 앱키, 앱시크릿, 계좌번호 및 실전투자 통신 엔드포인트 URL(`prod`)을 관리.
- **MCP(Model Context Protocol) 연동**:
  - `kis-code-assistant-mcp` 디렉토리에 위치한 MCP 서버를 통해, KIS API 관련 코딩 어시스턴트 역할을 지원하는 확장 도구가 포함되어 있음.

## 3. 기술 스택 (Tech Stack)
- **언어**: Python >= 3.12
- **프레임워크**: FastAPI
- **주요 라이브러리**: `apscheduler`, `requests`, `uvicorn` 등
- **버전 관리 및 의존성**: `pyproject.toml`, `uv.lock`

## 4. 실행 방법 (Run & Debug)
- **디버그 모드 실행**: 프로젝트 진입점에서 아래 명령어를 통해 핫 리로드(Hot Reload)가 활성화된 디버그 모드로 서버를 구동할 수 있음.
  ```bash
  uv run fastapi dev app/main.py
  ```
