# 에이전트 규칙 (Agent Rules)

- **언어 설정**: 항상 한국어로 대답할 것. (Always speak in Korean)
- **응답 태도**: 친절하고 명확하게 답변하며, 코드 작성 및 수정 시 프로젝트 아키텍처와 ADR 원칙을 철저히 준수할 것.
- **문서화 및 스펙 참조 원칙 (Context Engineering)**:
  - 본 `AGENTS.md`는 핵심 행동 강령과 불변 원칙만을 담는다.
  - 세부 아키텍처 및 구현 스펙은 반드시 `/docs` 폴더 내 문서를 `view_file`로 먼저 읽고 작업한다.
- 🛠️ **에이전트 스킬 활용 원칙**:
  - `using-agent-skills` 메타 스킬을 기본(Default)으로 적용하여 작업 단계에 맞는 최적의 스킬을 능동적으로 선택한다.
  - Pandas 데이터 처리 시 `pandas-pro`, FastAPI 백엔드 작업 시 `fastapi` 스킬 가이드라인을 최우선 적용한다.
- **불변 원칙**: 기존에 합의된 아키텍처 결정(ADR)이나 핵심 제약 조건을 사용자의 지시 없이 임의로 축소하거나 삭제하지 않는다.

---

# 프로젝트 개요 및 컨텍스트 맵

## 1. 개요 (Overview)
- **프로젝트명**: Trading Server & Dashboard
- **목적**: KIS OpenAPI를 활용한 2,400여 개 전 종목 시계열 수집/분석 및 **Zero-Latency 돌파(Breakout) 전략 자동 스크리너 & 차트 대시보드**.
- **인프라 제약**: Oracle Cloud Free Tier (1 OCPU, 1GB RAM) 최적화.
- **운영 환경**: 실전투자(PROD) 단일 모드 (모의투자 배제).

## 2. 도메인별 상세 문서 색인 (Context Sitemap)
⚠️ 작업 전 반드시 해당 도메인의 문서를 `view_file`로 읽고 스펙을 파악할 것:

| 도메인 | 참조 문서 | 핵심 내용 |
|---|---|---|
| **아키텍처 결정** | `docs/decisions/` | ADR-001 ~ ADR-035 (설계 배경, 대안, 트레이드오프) |
| **데이터베이스** | `docs/database.md` | In-Memory Shared DB, STRICT INTEGER, `daily_ma`/`minute_ma` 스키마 |
| **스케줄러 & 워커** | `docs/scheduler.md` | SystemScheduler 타임라인, Rate Limit Priority Queue, 지능형 GC |
| **스크리너 엔진** | `docs/screener.md` | Multi-Factor Dict, 휴리스틱 비용 정렬, Pre-calculated MA Push-down, SSE |
| **API & 엔드포인트** | `docs/endpoint.md` | SystemStateGuard (HTTP 503 Fail-fast), `/market`, `/api/screener` 스펙 |
| **프론트엔드 UI** | `docs/frontend.md` | Next.js 15+, Client-Side Aggregation, Lightweight Charts v5, Ranking View |
| **환경 설정** | `docs/environment.md`| `.env` (DEBUG, SCHED, LOG_LEVEL), `kis_devlp.yaml` 파라미터 가이드 |
| **배포 & CI/CD** | `docs/cicd.md` | GitHub Actions, Docker Volume (`./data:/app/data`), Nginx, SSL |

## 3. 기술 스택 및 실행 명령어
- **백엔드**: Python >= 3.12, FastAPI, APScheduler, SQLite3, `uv`
- **프론트엔드**: Next.js 15+ (App Router), TypeScript, Tailwind CSS, shadcn/ui, Lightweight Charts
- **실행 & 테스트 명령어**:
  ```bash
  # 로컬 디버그 모드 실행 (스케줄러 차단, 토큰 캐시 재사용)
  uv run fastapi dev app/main.py

  # 코드 린트 및 포맷
  uv run ruff check . --fix && uv run ruff format .
  ```

---

# 핵심 절대 원칙 (Boundaries & Invariants)

1. **메모리 보호 (1GB RAM & Multi-Factor Dict)**:
   - 2,400개 전 종목 시계열을 Pandas DataFrame으로 일괄 로드하거나 병합(`Merge`)하는 로직을 절대 작성하지 않는다.
   - 스크리너 다중 지표 연산은 가벼운 지표 딕셔너리(`Dict[str, Dict[str, float]]`)와 파이썬 내장 병합(`|`)으로만 수행한다 (참고: `ADR-014`, `ADR-028`).
2. **API Rate Limit & 타임아웃 방어**:
   - KIS 초당 20건 제한을 방어하는 `Global Rate-Limiting Queue`의 딜레이(`sleep(0.1)`)를 임의로 줄이거나 삭제하지 않는다.
   - 모든 HTTP 통신에는 `timeout=10` (인증은 `timeout=30`)을 필수 명시한다 (참고: `ADR-034`).
   - KIS 랭킹 API(`FHPTJ04400000`)의 30건 고정 반환 제약을 수용하여 Bulk 연산한다 (참고: `ADR-019`).
3. **Zero-Latency In-Memory MA & Push-down**:
   - 무거운 SQLite 윈도우 함수(`AVG OVER`)를 사용하지 않고, 수집 시 사전 계산된 In-Memory MA 테이블(`daily_ma`, `minute_ma`)을 단순 스캔한다 (참고: `ADR-026`).
   - 파라미터는 `VALID_MA_PERIODS` 화이트리스트 및 정수 검증을 거쳐 Parameterized Query(`WHERE ticker IN (?, ...)`)로 안전하게 주입한다 (참고: `ADR-027`, `ADR-033`).
4. **SQLite Connection Lifecycle & STRICT 정수 캐스팅**:
   - 백그라운드 워커에서 독립 연결 시 반드시 `try...finally: conn.close()`로 닫아 파일 락을 방지한다 (참고: `ADR-023`).
   - `STRICT` 테이블의 날짜/시간은 항상 `INTEGER` 형변환을 준수한다 (참고: `ADR-022`, `ADR-023`).
5. **글로벌 시스템 가드 (SystemStateGuard)**:
   - 지능형 GC(새벽 4시)나 부트스트랩 중에는 `system_state.acquire()`를 통해 일반 API 요청을 즉시 `HTTP 503`으로 거절(Fail-fast)한다 (`/health` 제외, 참고: `ADR-031`, `ADR-032`).
6. **테스트 격리 (DB Routing)**:
   - 파괴적 통합 테스트 수행 시 `test_db_var` (ContextVar)를 통해 `test_trading.db`로 우회 라우팅한다 (참고: `ADR-001`).
