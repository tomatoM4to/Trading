# 에이전트 규칙 (Agent Rules)

- **언어 설정**: 항상 한국어로 대답할 것. (Always speak in Korean)
- **응답 태도**: 사용자의 요청에 대해 친절하고 명확하게 답변하며, 코드 작성 및 수정 시 본 규칙 및 프로젝트 아키텍처를 철저히 준수할 것.
- **문서화 및 스펙 참조 원칙 (Context Engineering)**:
  - 본 `AGENTS.md`는 가장 핵심적인 행동 강령과 개요만을 담는다.
  - 프로젝트의 비대화를 방지하고 토큰을 절약하기 위해, **상세한 아키텍처 및 데이터베이스 스펙은 절대 이 파일에 적지 않으며 반드시 `/docs` 폴더 내의 마크다운 파일을 참조하거나 업데이트**한다.
  - ⚠️ 특정 분야의 작업 전, 반드시 아래의 문서를 `view_file` 도구로 읽고 스펙을 파악할 것:
    - **아키텍처 결정 기록(ADR)**: `docs/decisions/` 내의 `.md` 문서들
    - **DB 및 스키마 작업**: `docs/database.md`
    - **워커 및 스케줄러 작업**: `docs/scheduler.md`
    - **라우터 및 API 통신 작업**: `docs/endpoint.md`
- 🛠️ **에이전트 스킬 활용 원칙 (Meta-Skills & Custom Skills)**:
  - 사용자가 명시적으로 스킬을 지정하지 않더라도, 항상 내장된 **`using-agent-skills`** 메타 스킬을 기본(Default)으로 적용하여 현재 작업 단계(Phase)에 맞는 최적의 스킬(예: `spec-driven-development`, `incremental-implementation` 등)을 스스로 선택하고 그 워크플로우를 따른다.
  - Pandas 기반의 데이터 처리/분석(DataFrame 등) 작업 시, 항상 내장된 **`pandas-pro`** 스킬의 가이드라인을 최우선으로 적용한다.
  - 백엔드 API, 라우터, 의존성 주입 등 작업 시, 항상 내장된 **`fastapi`** 스킬의 가이드라인(Best Practices)을 철저히 준수한다.
- **불변 원칙**: 기존에 합의된 중요한 설계 원칙이나 규칙을 사용자의 명시적인 지시 없이 임의로 축소하거나 삭제하지 않는다.

---

# 프로젝트 스펙 (Project Specifications)

## 1. 개요 (Overview)
- **프로젝트명**: Trading Server
- **목적**: KIS OpenAPI를 활용하여 2,400여 개 전 종목을 수집/분석하고, **Zero-Latency Breakout(돌파) 전략 기반의 자동 매매 시스템** 구축. Oracle Cloud(1 OCPU/1GB)의 한계를 넘는 최적화 지향.
- **핵심 파이프라인**: 백그라운드 부트스트랩을 통한 시장별(KOSPI/KOSDAQ) 순차적 무중단 데이터 적재 메커니즘 운용.
- **멀티 레포지토리 / 멀티 디렉토리 구조 (예정)**: 현재 FastAPI 프로젝트이나 향후 웹(Next.js) 및 앱(React Native) 추가 예정.
- **운영 환경 (Environment)**: 모의투자 배제, 실전투자(PROD) 단일 모드.
- **설정 파일**: `kis_devlp.yaml`

## 2. 기술 스택 (Tech Stack)
- **언어**: Python >= 3.12
- **프레임워크**: FastAPI
- **주요 라이브러리**: `apscheduler`, `requests`, `pandas`, `uvicorn` 등
- **패키지 관리**: `uv` (`pyproject.toml`, `uv.lock`)

## 3. 로깅 체계 (Logging System)
- 일반적인 앱 상태 변경(INFO)과 백그라운드 스케줄러 작업 상태(SCHED)를 명확히 분리하여 콘솔 가독성을 극대화합니다.
- `logger.sched(...)` 라는 커스텀 레벨(Level 25)을 사용하여 스케줄러 작동 로그에 `[SCHED]` 태그를 시각적으로 강조합니다.

## 4. 실행 방법 (Run & Debug)
- **백엔드 디버그 모드 실행**:
  `.env` 파일에 `DEBUG=True` 설정 시 무거운 백그라운드 스케줄러가 차단되어 단건 API 테스트에 용이합니다.
  ```bash
  uv run fastapi dev app/main.py
  ```
- **코드 린팅 및 자동 포매팅 (Ruff)**:
  ```bash
  uv run ruff check . --fix
  uv run ruff format .
  ```

## 5. 절대 원칙 (Boundaries)
- **메모리 제한**: 1GB RAM 환경이므로 전 종목(2,400개) 데이터를 한 번에 메모리에 올리거나 Pandas로 대규모 병합(Merge)하는 로직을 절대 작성하지 않는다. (항상 Chunk 단위나 SQLite 내부 쿼리로 해결할 것)
- **API Rate Limit 방어**: KIS API의 초당 20회 통신 제한을 방어하는 `Global Rate-Limiting Queue`의 딜레이 시간(`sleep(0.1)`)을 임의로 줄이거나 삭제하지 않는다.
- **보안 및 자격 증명**: `.env` 파일의 내용이나 KIS API Secret 정보를 소스 코드에 절대 하드코딩하지 않는다.

## 6. 핵심 코드 패턴 (Patterns)
- **로깅 규칙**: 스케줄러 및 백그라운드 작업의 로깅은 표준 `info` 대신 반드시 커스텀 레벨인 `logger.sched(...)`를 사용하여 로그 가독성을 유지한다.
- **API 래퍼 사용**: KIS OpenAPI 호출 결과는 반드시 사전에 정의된 `APIResp` 객체(내부 `DotDict` 포함)로 래핑하여 파이썬 점 표기법(Dot-notation)으로 일관성 있게 다룬다.
- **테스트 환경 격리 (DB Routing)**: 무결성 검증이나 파괴적인 통합 테스트(삭제/복구)를 수행할 때 운영 DB(`trading.db`)를 오염시키지 않도록, `contextvars.ContextVar`(`test_db_var`)를 활용해 런타임에 동적으로 `test_trading.db`로 라우팅하는 패턴을 반드시 준수한다.
