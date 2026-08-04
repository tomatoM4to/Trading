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
    - **프론트엔드 및 UI 작업**: `docs/frontend.md`
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
  `.env` 파일에 `DEBUG=True` 설정 시 무거운 백그라운드 스케줄러가 차단되어 단건 API 테스트에 용이합니다. 또한 서버 부팅 시 KIS API 토큰을 강제로 재발급하지 않고 캐시를 재사용하여 API 호출을 절약합니다. 반대로 운영 환경(`DEBUG=False`)에서는 배포/재시작 시 항상 안전하게 새 토큰을 강제 발급(`force=True`)합니다. (참고: `docs/decisions/ADR-007-dynamic-auth-token-issuance.md`)
  ```bash
  uv run fastapi dev app/main.py
  ```
- **코드 린팅 및 자동 포매팅 (Ruff)**:
  ```bash
  uv run ruff check . --fix
  uv run ruff format .
  ```

## 5. 절대 원칙 (Boundaries)
- **메모리 제한 (Set-Theory Pipeline)**: 1GB RAM 환경이므로 전 종목(2,400개) 데이터를 한 번에 메모리에 올리거나 Pandas로 대규모 병합(Merge)하는 로직을 절대 작성하지 않는다. 스크리너나 다중 지표 교집합 연산을 수행할 때는 반드시 **종목 코드 집합(`Set[str]`) 단위로만 데이터를 교환하고, 파이썬 내장 `&` (교집합) 연산**으로 메모리 사용을 최소화한다. (참고: `ADR-014`)
- **API Rate Limit 방어**: KIS API의 초당 20회 통신 제한을 방어하는 `Global Rate-Limiting Queue`의 딜레이 시간(`sleep(0.1)`)을 임의로 줄이거나 삭제하지 않는다. 스크리너 연산 시 외부 수급 API 등은 '지연 평가(Late Evaluation)' 또는 '랭킹 Bulk 호출'로 N+1 문제를 원천 차단한다.
- **보안 및 자격 증명**: `.env` 파일의 내용이나 KIS API Secret 정보를 소스 코드에 절대 하드코딩하지 않는다.
- **KIS 랭킹 API 제약 수용**: `FHPTJ04400000` (외국인/기관 가집계) 등 특정 KIS 랭킹 API는 HTS 화면과 동일하게 최대 30건만 고정 반환하며 연속조회(`tr_cont`)를 지원하지 않습니다. 억지로 페이지네이션을 구현하거나 개별 종목 N+1 호출로 우회하려 하지 말고 30건 제약을 그대로 수용하여 Bulk 연산을 수행합니다. (참고: `docs/decisions/ADR-019-kis-ranking-api-30-limit.md`)

## 6. 핵심 코드 패턴 (Patterns)
- **SQLite Push-down & 엄격한 윈도우 연산**: 이평선 정배열 및 크로스 등 기술적 지표 필터링은 파이썬으로 데이터를 가져오지 않고, SQLite Window Function(`LAG`, `ROW_NUMBER` 등)과 CTE를 활용해 DB 엔진 단에서 조건을 판별(Push-down)하고 결과 Ticker만 반환하도록 작성한다. 또한 데이터(캔들) 개수가 부족할 때 발생하는 수학적 왜곡(False Positive)을 막기 위해 윈도우 연산 시 반드시 `CASE WHEN COUNT(...) = N` 조건으로 데이터 무결성을 검증하고 실패 시 `NULL`을 리턴해야 한다. (참고: `ADR-016`)
- **Push-down 파라미터 엄격 검증 (Anti-Short-Circuit)**: SQLite 쿼리 옵티마이저가 `1=0`과 같은 더미 조건으로 인해 전체 무거운 CTE 연산을 건너뛰는(Short-circuit) 버그를 막기 위해, 스크리너 필터 핸들러는 SQL 문자열을 조립하기 전 반드시 모든 파라미터를 엄격하게 검증(Validation)하고 잘못된 값일 경우 예외(ValueError)를 던져야 한다. (참고: `ADR-021`)
- **스크리너 Pre-filter 최적화 (파티션 축소)**: 윈도우 함수 등 무거운 연산을 수행하는 스크리너 쿼리는 연산 전 반드시 `WITH active_tickers` CTE를 사용하여 `stock_codes` 테이블에서 매매 불가 종목(거래정지 `is_halted=1`, 관리종목 `is_admin_issue=1`)을 선행 필터링(Pre-filter)한 후 메인 테이블과 조인해야 한다. 이를 통해 윈도우 함수가 불필요한 종목까지 파티셔닝하는 리소스 낭비를 원천 차단한다. (참고: `ADR-020`)
- **스칼라 서브쿼리를 이용한 데이터 확장 (Enrichment)**: 스크리너 등에서 소수의 결과 집합(Result Set)에 대한 추가 지표(최신 현재가, 거래대금 등)를 가져올 때는 무거운 JOIN이나 파이썬 맵핑 대신, SELECT 절 내부에 `ORDER BY date DESC LIMIT 1` 형태의 스칼라 서브쿼리를 작성하여 B-Tree 인덱스 스캔을 유도한다. (참고: `ADR-017`)
- **실시간 점진적 피드백 (Progressive Feedback)**: 다중 교집합(스크리너 등)과 같이 연산이 길어져 1분 이상 걸릴 수 있는 무거운 파이프라인 실행 시, 클라이언트 타임아웃 방지 및 좋은 UX를 위해 별도의 비동기 큐 없이 FastAPI의 `StreamingResponse(text/event-stream)`를 활용한 SSE 방식을 최우선 적용한다. (참고: `ADR-018`)
- **로깅 규칙**: 스케줄러 및 백그라운드 작업의 로깅은 표준 `info` 대신 반드시 커스텀 레벨인 `logger.sched(...)`를 사용하여 로그 가독성을 유지한다.
- **API 래퍼 사용**: KIS OpenAPI 호출 결과는 반드시 사전에 정의된 `APIResp` 객체(내부 `DotDict` 포함)로 래핑하여 파이썬 점 표기법(Dot-notation)으로 일관성 있게 다룬다.
- **UI/UX 원칙 (Smart Defaults)**: 강제 제약(Systematic restriction)보다는 사용자의 편의를 돕는 '스마트 디폴트' 패턴을 지향한다. (예: 타임프레임 전환 시 관련 이평선 자동 On/Off)
    - **테스트 환경 격리 (DB Routing)**: 무결성 검증이나 파괴적인 통합 테스트(삭제/복구)를 수행할 때 운영 DB(`trading.db`)를 오염시키지 않도록, `contextvars.ContextVar`(`test_db_var`)를 활용해 런타임에 동적으로 `test_trading.db`로 라우팅하는 패턴을 반드시 준수한다.
  - ⚠️ 단, 단순 상태 점검을 위한 순수 조회(Read-only) 모니터링 API(`/admin/live/...`)는 우회 없이 실제 운영 DB를 직접 조회한다.

## 7. 배포 및 CI/CD 파이프라인 (CI/CD Pipeline)
- **자세한 구조는 `docs/cicd.md` 참고.**
- **초기 서버 세팅**: `.github/workflows/setup-server.yml` (수동 트리거). 배포 경로(`~/Trading`) 생성, `.env` 및 `kis_devlp.yaml` 파일 동적 생성, 초기 SSL 발급을 수행한다. (`init-cert.sh`는 비대화형 모드로 순수하게 발급만 수행하며, 컨테이너 기동은 수행하지 않음)
- **자동 배포**: `.github/workflows/deploy.yml` (`main` Push 트리거). 도커 이미지 빌드 후 서버로 전송하며, 시크릿 변수 갱신을 위해 `kis_devlp.yaml`을 재생성한 뒤 `docker compose up -d`를 수행한다. (Sudo 권한 상승 시 환경 변수 유실을 막기 위해 `sudo -E` 활용)
- **설정 파일 동적 생성 원칙**: `.env` 및 `kis_devlp.yaml`은 보안상 `.gitignore`에 등록되어 도커 이미지에 포함되지 않으므로, GitHub Actions가 SSH 접속 시 GitHub Secrets 값을 이용해 서버에 직접 동적 생성(Echo/Cat)하고 도커 볼륨으로 마운트하는 패턴을 유지한다. (참고: `docs/decisions/ADR-006-dynamic-config-generation.md`)
- **Docker 데이터 영속성 원칙**: OCI 서버에 배포 시 도커 컨테이너 내의 코드를 호스트의 빈 폴더로 덮어쓰는 행위나 SQLite WAL 모드를 단일 파일로 마운트하는 행위를 엄격히 금지하며, 반드시 전용 데이터 폴더(`./data:/app/data`)를 마운트한다. (참고: `docs/decisions/ADR-005-docker-sqlite-persistence-strategy.md`)

## 8. 외부 의존성 및 MCP 관리 (External Dependencies)
- **Git Submodule 원칙**: 외부에서 제공되는 MCP(Model Context Protocol) 서버 코드나 타 레포지토리의 소스 코드는 직접 복사/붙여넣기하여 프로젝트에 하드코딩하지 않습니다. 반드시 `git submodule`을 통해 연동하여 메인 프로젝트의 Git 로그 오염을 방지하고 공식 업스트림의 업데이트 추적을 용이하게 합니다.
- **Sparse-Checkout 적용**: 무거운 원본 레포지토리 전체가 워크스페이스를 어지럽히지 않도록, `git sparse-checkout`을 적용하여 필요한 특정 하위 폴더(예: `MCP/KIS Code Assistant MCP`)만 로컬에 노출시키는 패턴을 유지합니다. (참고: `docs/decisions/ADR-012-mcp-submodule-migration.md`)
