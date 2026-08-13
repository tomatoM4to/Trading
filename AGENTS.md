# 에이전트 규칙 (Agent Rules)

- **언어 설정**: 항상 한국어로 대답할 것. (Always speak in Korean)
- **응답 태도**: 사용자의 요청에 대해 친절하고 명확하게 답변하며, 코드 작성 및 수정 시 본 규칙 및 프로젝트 아키텍처를 철저히 준수할 것.
- **문서화 및 스펙 참조 원칙 (Context Engineering)**:
  - 본 `AGENTS.md`는 가장 핵심적인 행동 강령과 개요만을 담는다.
  - 프로젝트의 비대화를 방지하고 토큰을 절약하기 위해, **상세한 아키텍처 및 데이터베이스 스펙은 절대 이 파일에 적지 않으며 반드시 `/docs` 폴더 내의 마크다운 파일을 참조하거나 업데이트**한다.
  - ⚠️ 특정 분야의 작업 전, 반드시 아래의 문서를 `view_file` 도구로 읽고 스펙을 파악할 것:
    - **아키텍처 결정 기록(ADR)**: `docs/decisions/` 내의 `.md` 문서들
    - **기능 명세서(Specs)**: `docs/specs/` 내의 `.md` 문서들
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
- **메모리 제한 (Multi-Factor Dict Pipeline)**: 1GB RAM 환경이므로 전 종목(2,400개) 데이터를 한 번에 메모리에 올리거나 Pandas로 대규모 병합(Merge)하는 로직을 절대 작성하지 않는다. 스크리너 다중 지표 교집합 연산을 수행할 때는 종목 통과 여부뿐만 아니라 지표 값(Float)을 담은 딕셔너리(`Dict[str, Dict[str, float]]`) 단위로 데이터를 교환하며, 파이썬 내장 딕셔너리 병합(`|`) 및 키(Key) 교집합을 활용해 메모리 낭비를 방지한다. 이를 통해 프론트엔드에서 Zero-Latency 다중 정렬을 지원한다. (참고: `ADR-014`, `ADR-028`)
- **API Rate Limit 및 타임아웃 방어**: KIS API의 초당 20회 통신 제한을 방어하는 `Global Rate-Limiting Queue`의 딜레이 시간(`sleep(0.1)`)을 임의로 줄이거나 삭제하지 않는다. 스크리너 연산 시 외부 수급 API 등은 '지연 평가(Late Evaluation)' 또는 '랭킹 Bulk 호출'로 N+1 문제를 원천 차단한다. 추가로, 무한 대기로 인한 스레드 고갈 방지를 위해 모든 `requests` 통신에는 반드시 `timeout=10` (인증은 `timeout=30`)을 명시한다. (참고: `ADR-034`)
- **보안 및 자격 증명**: `.env` 파일의 내용이나 KIS API Secret 정보를 소스 코드에 절대 하드코딩하지 않는다.
- **KIS 랭킹 API 제약 수용**: `FHPTJ04400000` (외국인/기관 가집계) 등 특정 KIS 랭킹 API는 HTS 화면과 동일하게 최대 30건만 고정 반환하며 연속조회(`tr_cont`)를 지원하지 않습니다. 억지로 페이지네이션을 구현하거나 개별 종목 N+1 호출로 우회하려 하지 말고 30건 제약을 그대로 수용하여 Bulk 연산을 수행합니다. (참고: `docs/decisions/ADR-019-kis-ranking-api-30-limit.md`)

## 6. 핵심 코드 패턴 (Patterns)
- **In-Memory Zero-Latency 튜닝 (Memory & STRICT)**: 물리 디스크의 I/O 병목을 제거하기 위해 서버 부팅 시 DB를 `file::memory:?cache=shared`로 100% 로드하며, 익명 메모리 DB가 휘발되지 않도록 전역 `_keepalive_conn`을 유지한다. RAM 낭비 방지를 위해 모든 테이블은 `WITHOUT ROWID, STRICT` 속성을 갖추고 `date` 및 `time` 데이터는 `INTEGER`로 극한 압축한다. 임시 연산 역시 `PRAGMA temp_store = MEMORY`로 강제한다. (참고: `ADR-022`)
- **SQLite Connection Lifecycle 및 파일 락 방어**: 파이썬의 `with sqlite3.connect(...)`는 트랜잭션만 관리할 뿐 커넥션을 닫아주지 않으므로 파일 잠금(WinError 32)을 유발할 수 있다. 백그라운드 워커 등에서 단독으로 DB에 연결할 때는 **반드시 `try...finally: conn.close()` 패턴을 명시적으로 사용**해야 한다. 단, API 엔드포인트는 `get_db()` 의존성을 통해 프레임워크 단에서 안전하게 종료된다. (참고: `ADR-023`)
- **STRICT INTEGER 타입 캐스팅**: `STRICT` 테이블의 `INTEGER` 컬럼(예: 날짜, 시간)을 다룰 때, 파라미터로 주입할 변수(문자열 날짜)는 반드시 `int()`로 캐스팅하여 쿼리를 수행해야 Type Mismatch 에러를 방지할 수 있으며, 반대로 파이썬 딕셔너리로 쿼리 결과를 만들 때 KIS API의 문자열 응답과 비교하려면 반드시 `str(row["date"])` 처럼 명시적 캐스팅을 거쳐야만 탐색 누락(Missing)을 방지할 수 있다. (참고: `ADR-023`)
- **순수 파이썬 캐시를 통한 인메모리 MA (Zero-Latency)**: 극단적인 스크리너 속도를 위해, 무거운 SQLite 윈도우 함수(`AVG OVER`)를 전면 폐기하고, 백그라운드 스케줄러가 캔들(OHLCV)을 수집할 때 파이썬 내장 `collections.deque` 기반의 `MACalculator`에 값을 밀어 넣어 즉시 MA를 연산한다. 산출된 MA 값은 물리 디스크가 아닌 전용 휘발성 인메모리 DB(`daily_ma`, `minute_ma`)에만 저장하여 디스크 I/O를 원천 차단한다. 데이터 부족으로 인한 왜곡(False Positive) 방지 역시 윈도우 함수 대신 파이썬 `deque`의 길이 검증으로 대체되었다. (참고: `ADR-026`)
- **초경량 스크리너 쿼리 (Pre-calculated Push-down) 및 AST 인젝션 방어**: 스크리너 파이프라인의 이평선 조건식(정배열, 크로스 등)은 윈도우 연산 없이 인메모리 MA 테이블의 이미 계산된 컬럼(`ma5`, `ma20` 등)을 단순 스캔하는 방식(`SELECT ... FROM daily_ma`)으로 작동한다. 클라이언트로부터 입력받은 이평선 및 기간 조건은 AST 인젝션 공격을 방지하기 위해 엄격한 화이트리스트(`VALID_MA_PERIODS`)와 정수 바운드 검증을 반드시 거쳐야 한다. 또한 오버헤드를 막기 위해 파이썬 레벨에서 이전 체인의 `chain_set`을 쿼리의 `WHERE ticker IN (?, ...)` 구문에 파라미터(Parameterized Query)로 안전하게 주입하여 파서 오버헤드를 제거한다. (참고: `ADR-026`, `ADR-027`, `ADR-033`)
- **스크리너 Pre-filter 최적화 (파티션 축소)**: 윈도우 함수 등 무거운 연산을 수행하는 스크리너 쿼리는 연산 전 반드시 `WITH active_tickers` CTE를 사용하여 매매 불가 종목을 선행 필터링한 후 조인한다.
- **초경량 매물대/이격도 스크리닝 (Cross-DB Join & Approximation)**: 1GB RAM 서버의 디스크 I/O를 방지하기 위해 이격도와 매물대는 적재 시 사전 연산하지 않습니다. 이격도는 스크리너 실행 시점(Run-time)에 `ATTACH DATABASE` 구문을 통해 메인 DB(`daily_ohlcv`)와 인메모리 전용 MA DB(`daily_ma`)를 단일 트랜잭션으로 조인하여 실시간 푸시다운 연산합니다. 또한 무거운 매물대(Volume Profile) 지표는 정밀 분할 대신 `ORDER BY volume DESC LIMIT 1` 서브쿼리를 이용해 '지정 기간 내 최대 거래량 캔들'을 핵심 저항선으로 삼는 초경량 근사(Approximation) 기법으로 압축합니다. (참고: `ADR-035`)
- **스칼라 서브쿼리를 이용한 데이터 확장 (Enrichment)**: 스크리너 등에서 소수의 결과 집합(Result Set)에 대한 추가 지표(최신 현재가, 거래대금 등)를 가져올 때는 무거운 JOIN이나 파이썬 맵핑 대신, SELECT 절 내부에 `ORDER BY date DESC LIMIT 1` 형태의 스칼라 서브쿼리를 작성하여 B-Tree 인덱스 스캔을 유도한다. (참고: `ADR-017`)
- **실시간 점진적 피드백 (Progressive Feedback)**: 다중 교집합(스크리너 등)과 같이 연산이 길어져 1분 이상 걸릴 수 있는 무거운 파이프라인 실행 시, 클라이언트 타임아웃 방지 및 좋은 UX를 위해 별도의 비동기 큐 없이 FastAPI의 `StreamingResponse(text/event-stream)`를 활용한 SSE 방식을 최우선 적용한다. (참고: `ADR-018`)
- **스크리너 AST 파이프라인 최적화 (Big O Heuristics)**: 클라이언트의 조건식(AST)은 서버 메모리 보호 및 성능 극대화를 위해 반드시 `OR` 기준으로 분기(Split) 후, 각 `AND` 체인 내부를 **휴리스틱 비용(Cost)** 기준으로 정렬(가벼운 필터 우선)하여 실행한다. In-Memory MA 구조 하에서는 윈도우 크기(`max_window`)가 아닌 실제 스캔 행 수(`duration`)만을 기반으로 DB 비용을 정확히 산정해야 한다. API 호출 필터(외국인/기관 매수 등)는 결과 셋을 30개로 극적으로 줄여주므로 항상 Cost 0 (최우선순위)으로 취급한다. 중간 교집합 연산 시 `Set`이 빈약해지면 후속 연산을 즉시 중단(Short-circuit)한다. (참고: `ADR-024`, `ADR-027`)
- **지능형 가비지 컬렉터 (Intelligent GC)**: 캘린더 시간 경과로 인한 데이터 소실(휴일 누락 등)을 막기 위해, 새벽 4시에 스마트 트리거(어제 휴장 여부 판별)를 거친 후, SQLite `TEMP TABLE`과 윈도우 함수를 이용한 단일 트랜잭션 해시 조인으로 각 종목 고유의 N영업일(분봉 2일, 일봉 500일) 컷오프를 계산해 일괄 삭제합니다. 파이썬 단의 for-loop `DELETE`는 극심한 파일 락을 유발하므로 엄격히 금지됩니다. (참고: `ADR-031`)
- **글로벌 API 차단기 (System State Guard)**: 1 OCPU/1GB RAM 서버의 생존을 위해, 지능형 GC나 콜드스타트 등 무거운 백그라운드 작업 수행 시 `system_state.acquire()` 컨텍스트 매니저를 통해 전역 상태를 잠글 수 있습니다. 잠긴 동안 인입되는 모든 API(모니터링용 `/health` 제외) 요청은 큐잉 없이 즉시 HTTP 503 코드와 함께 거절(Fail-fast)되어 OOM 및 파일 락을 완벽히 방지합니다. (참고: `ADR-032`)
- **로깅 규칙**: 스케줄러 및 백그라운드 작업의 로깅은 표준 `info` 대신 반드시 커스텀 레벨인 `logger.sched(...)`를 사용하여 로그 가독성을 유지한다. (일반 `info` 사용 금지) 워커 등에서 단독으로 DB에 연결할 때는 **반드시 `try...finally: conn.close()` 패턴을 명시적으로 사용**해야 한다. 단, API 엔드포인트는 `get_db()` 의존성을 통해 프레임워크 단에서 안전하게 종료된다. (참고: `ADR-023`)
- **API 래퍼 사용**: KIS OpenAPI 호출 결과는 반드시 사전에 정의된 `APIResp` 객체(내부 `DotDict` 포함)로 래핑하여 파이썬 점 표기법(Dot-notation)으로 일관성 있게 다룬다.
- **UI/UX 원칙 (Smart Defaults & Mobile-First)**: 강제 제약(Systematic restriction)보다는 사용자의 편의를 돕는 '스마트 디폴트' 패턴을 지향한다. (예: UI는 직관적인 숫자(5, 10)만 노출하고 타임프레임에 맞춰 백엔드 키를 자동 매핑). 또한 모바일 사용성을 위해 불필요한 중복 테두리(Double-border)를 걷어내고 `ResizeObserver`를 통해 DOM의 유동적 크기에 차트가 대응하도록 설계한다.
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
