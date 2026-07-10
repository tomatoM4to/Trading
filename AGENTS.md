# 에이전트 규칙 (Agent Rules)

- **언어 설정**: 항상 한국어로 대답할 것. (Always speak in Korean)
- **응답 태도**: 사용자의 요청에 대해 친절하고 명확하게 답변하며, 코드 작성 및 수정 시 본 규칙 및 프로젝트 아키텍처를 철저히 준수할 것.
- **문서화 및 스펙 참조 원칙 (Context Engineering)**:
  - 본 `AGENTS.md`는 가장 핵심적인 행동 강령과 개요만을 담는다.
  - 프로젝트의 비대화를 방지하고 토큰을 절약하기 위해, **상세한 아키텍처 및 데이터베이스 스펙은 절대 이 파일에 적지 않으며 반드시 `/docs` 폴더 내의 마크다운 파일을 참조하거나 업데이트**한다.
  - ⚠️ 특정 분야의 작업 전, 반드시 아래의 문서를 `view_file` 도구로 읽고 스펙을 파악할 것:
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
  ```bash
  uv run fastapi dev app/main.py
  ```
- **코드 린팅 및 자동 포매팅 (Ruff)**:
  ```bash
  uv run ruff check . --fix
  uv run ruff format .
  ```
