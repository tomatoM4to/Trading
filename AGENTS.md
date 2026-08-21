# Trading Server & Dashboard 에이전트 규칙

## 1. 역할과 응답 규칙

- 항상 한국어로 친절하고 명확하게 답한다.
- 현재 동작의 최종 근거는 테스트 가능한 코드다. 문서보다 코드를, 추측보다 확인을 우선한다.
- 작업 전에 이 파일과 작업 도메인에 해당하는 `/docs` 문서를 읽고, 수정할 소스와 관련 타입·테스트·유사 구현을 확인한다.
- 문서와 코드가 충돌하면 임의로 선택하지 말고 충돌을 밝힌다. 버그 수정 요청이 아니라면 코드를 문서에 맞추지 않는다.
- 사용자가 요구하지 않은 리팩터링, 기능 추가, 의존성 변경, 스키마 변경은 하지 않는다.
- 기존 변경은 사용자의 작업으로 간주하고 보존한다.

## 2. 프로젝트 목적

KIS OpenAPI로 국내 약 2,400개 종목의 일봉·분봉을 수집하고, 로컬 SQLite 데이터만으로 돌파 전략 스크리닝과 차트 조회를 제공한다. 운영 대상은 실전투자(PROD)이며 Oracle Cloud Free Tier의 1 OCPU·1GB RAM 제약을 전제로 한다.

핵심 목표는 다음 순서로 판단한다.

1. 데이터 무결성과 운영 계좌의 안전
2. 1GB 메모리 한도 내 생존성
3. KIS 호출 제한 준수
4. 장중 조회 지연 최소화
5. 구현과 운영의 단순성

## 3. 설계 철학

### 로컬 데이터 우선

- 사용자 조회 경로는 가능한 한 KIS API를 직접 호출하지 않고 이미 수집한 SQLite 데이터를 사용한다.
- 장중 외부 API 장애가 조회 API 전체 장애로 번지지 않게 한다.
- KIS 실시간 호출이 필요한 기능은 반드시 전역 우선순위 큐를 통과한다.

### 메모리는 빠르게, 디스크는 안전하게

- 주 데이터는 Shared In-Memory SQLite에서 서비스하고 `data/trading.db`는 영속 백업으로 사용한다.
- 이동평균은 별도 Shared In-Memory DB의 `daily_ma`, `minute_ma`에 유지한다.
- 메모리 DB 수명을 유지하는 keep-alive 연결을 임의로 제거하지 않는다.
- 무거운 작업 뒤에는 정해진 디스크 동기화 경로를 사용한다.

### 전 종목 연산은 작게

- 2,400개 전 종목 시계열을 하나의 Pandas DataFrame으로 적재하거나 병합하지 않는다.
- 스크리너 중간 결과는 `dict[str, dict[str, float]]`와 파이썬 내장 집합·딕셔너리 연산을 사용한다.
- SQL에서 후보군을 먼저 줄이고 필요한 데이터만 반환한다.
- 단일 종목 차트용 윈도 함수와 전 종목 스크리너 쿼리를 같은 비용으로 간주하지 않는다. 전 종목 경로에는 사전 계산 MA를 우선한다.

### 실패는 빠르고 복구 가능하게

- 부트스트랩, GC, 마스터 동기화처럼 데이터 상태를 바꾸는 작업은 `system_state.acquire()`로 일반 API를 503 차단한다.
- `/health`만 시스템 가드를 우회한다.
- 외부 HTTP 요청은 일반 호출 `timeout=10`, 인증 호출 `timeout=30`을 명시한다.
- 백그라운드 SQLite 연결은 `try/finally`에서 반드시 닫는다.
- 날짜와 시간은 STRICT 스키마에 맞춰 항상 `INTEGER`로 저장한다.

### 입력은 신뢰하지 않는다

- 동적 SQL의 값은 바인딩 파라미터를 사용한다.
- 컬럼명처럼 바인딩할 수 없는 식별자는 정적 화이트리스트로만 선택한다.
- 이동평균 기간은 `5, 10, 20, 60, 120, 200`만 허용한다.
- 스크리너의 기간, 임계값, 방향, limit은 타입과 범위를 검증한 뒤 쿼리에 사용한다.
- 관리자·테스트 엔드포인트는 운영상 민감한 인터페이스로 취급한다.

### 단일 운영 모드

- 모의투자 지원을 새로 추가하거나 실전/모의 분기를 확장하지 않는다.
- 인증 설정은 실전 키와 실전 API URL을 기준으로 유지한다.

## 4. 불변 경계

- KIS 큐의 `asyncio.sleep(0.1)`을 줄이거나 제거하지 않는다.
- 인증을 제외한 모든 외부 HTTP 호출의 10초 타임아웃을 제거하지 않는다.
- KIS 투자자 랭킹 API의 최대 30건 반환 제약을 우회한다고 가정하지 않는다.
- `VALID_MA_PERIODS` 검증 없이 요청 문자열을 SQL 식별자로 보간하지 않는다.
- 운영 데이터에 영향을 주는 통합 검증은 `test_db_var`로 테스트 DB에 라우팅한다.
- SQLite context manager가 연결을 닫는다고 가정하지 않는다. 연결은 명시적으로 닫는다.
- 합의 없이 핵심 테이블, 시스템 가드, 전역 KIS 큐, 메모리 DB 구조를 삭제하거나 축소하지 않는다.
- `.env`, `kis_devlp.yaml`, 토큰 캐시, DB 파일을 커밋하지 않는다.

## 5. 컨텍스트 라우팅

작업에 필요한 문서만 선택해서 읽는다.

| 작업 영역 | 먼저 읽을 문서 |
|---|---|
| 전체 구조·모듈 경계 | `docs/architecture.md` |
| SQLite·스키마·수명주기 | `docs/database.md` |
| KIS 인증·호출 큐 | `docs/kis-integration.md` |
| 스케줄러·수집·GC | `docs/scheduler.md` |
| 스크리너 AST·SSE | `docs/screener.md` |
| FastAPI 라우트·계약 | `docs/api.md` |
| Next.js·차트·UI | `docs/frontend.md` 및 `web/AGENTS.md` |
| 환경 변수·로컬 실행 | `docs/environment.md` |
| Docker·GitHub Actions·Nginx | `docs/deployment.md` |
| 검증·운영 점검 | `docs/operations.md` |

`open-trading-api/`는 KIS 공식 예제 서브모듈이다. 프로젝트 소유 코드가 아니므로 참고 자료로만 사용하고, 명시적 요청 없이 수정하지 않는다.

## 6. 기술 스택과 명령어

- 백엔드: Python 3.12+, FastAPI, APScheduler, SQLite, requests, uv
- 프론트엔드: Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Lightweight Charts 5
- 인프라: Docker Compose, Nginx, Certbot, GitHub Actions, GHCR

```powershell
# 백엔드 개발 서버
uv run fastapi dev app/main.py

# 백엔드 정적 검사와 포맷
uv run ruff check .
uv run ruff format --check .

# 프론트엔드
cd web
npm run dev
npm run lint
npx tsc --noEmit
npm run build
```

현재 독립 자동 테스트 스위트는 없다. 테스트를 추가하기 전까지 Ruff, TypeScript, ESLint, 프로덕션 빌드와 영향 경로의 수동 검증을 최소 완료 조건으로 삼는다.

## 7. 작업 완료 기준

- 관련 문서와 구현이 서로 일치한다.
- 입력 검증, 연결 종료, 타임아웃, 메모리 한도를 다시 확인한다.
- 가능한 정적 검사와 빌드를 통과한다.
- 실패하거나 실행하지 못한 검증을 숨기지 않는다.
- 변경 파일, 검증 결과, 남은 위험을 사용자에게 명확히 전달한다.
