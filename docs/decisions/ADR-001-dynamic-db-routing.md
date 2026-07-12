# ADR-001: ContextVar를 이용한 동적 데이터베이스 라우팅 (Dynamic DB Routing)

## Status
Accepted

## Date
2026-07-12

## Context
본 프로젝트는 KIS OpenAPI를 통해 전 종목(2,400여 개)의 일봉 및 분봉 데이터를 SQLite 기반의 단일 데이터베이스(`trading.db`)에 무중단으로 수집/적재하고 있습니다. 
이 과정에서 백그라운드 스케줄러의 동작 무결성을 검증하기 위해 **관리자 통합 테스트(콜드스타트 수집 ➡️ 고의 데이터 삭제 ➡️ 갭필 복구 ➡️ 무결성 1:1 비교)** 기능이 필수적으로 요구되었습니다.
하지만, 이러한 파괴적인 테스트를 라이브 스케줄러 로직을 그대로 사용하면서 수행할 경우 운영 환경의 `trading.db`가 오염되거나 락(Lock)에 걸려 실제 트레이딩이 마비될 심각한 위험이 있었습니다.

## Decision
Python의 `contextvars.ContextVar`를 활용하여 **런타임 시 요청(Request/Task) 단위로 타겟 데이터베이스 파일을 동적으로 우회(Routing)** 하는 패턴을 도입합니다.

1. `core.database` 모듈에 `test_db_var = ContextVar("test_db_var", default=None)`를 선언합니다.
2. `connect_sqlite()` 함수 내부에서 `test_db_var.get()`을 체크하여, 값이 존재하면 운영 DB(`trading.db`) 대신 해당 값(테스트 DB 경로)으로 SQLite Connection을 맺습니다.
3. 테스트 엔드포인트(`routes/admin.py`) 호출 시, `token = test_db_var.set(test_db_path)`를 설정하고, `try-finally` 블록을 통해 작업이 끝나면 반드시 `test_db_var.reset(token)`으로 컨텍스트를 복구합니다.

## Alternatives Considered

### 1. 전역 변수(Global Variable) 또는 Singleton 토글 사용
- **Pros**: 구현이 매우 단순합니다.
- **Cons**: FastAPI는 비동기 멀티스레드/멀티태스킹 환경이므로, 한 사용자가 테스트 엔드포인트를 호출하여 전역 변수를 `test_trading.db`로 바꾼 순간, 동시에 들어온 일반 사용자의 퍼블릭 마켓 API 요청마저도 `test_trading.db`를 바라보게 되는 치명적인 **Race Condition(경합 조건)**이 발생합니다.
- **Rejected**: 동시성 환경에서 데이터 정합성을 보장할 수 없으므로 기각되었습니다.

### 2. 의존성 주입 (Dependency Injection, Depends)
- **Pros**: FastAPI의 표준적이고 권장되는 방식입니다.
- **Cons**: 스케줄러를 포함한 백그라운드 태스크나 `main.py`의 `lifespan` 훅과 같이 FastAPI Request 컨텍스트 바깥에서 실행되는 로직에서는 `Depends`를 통한 DB 세션 주입이 극도로 번거롭거나 불가능합니다. 
- **Rejected**: 시스템 전반(백그라운드 스케줄러, 워커 함수 등)에 걸쳐 코드 수정이 대대적으로 일어나야 하며, 함수 파라미터가 릴레이처럼 길어지는 현상이 발생하여 기각되었습니다.

## Consequences
- **Positive**:
  - 기존의 백그라운드 워커 함수나 서비스 로직(`fetch_and_save_ohlcv`, `process_ticker` 등)의 서명을 단 한 줄도 수정하지 않고도, 호출하는 진입점(Controller)에서만 DB 타겟을 투명하게 바꿀 수 있습니다.
  - 비동기 Task 간 완벽한 격리가 이루어져 운영 환경을 100% 보호하면서도 파괴적인 통합 테스트가 가능해졌습니다.
- **Negative / Risks**:
  - `ContextVar`의 존재를 모르는 새로운 개발자(또는 에이전트)는 DB가 마법처럼 바뀌는 현상(Magic)으로 인해 디버깅 시 혼란을 겪을 수 있습니다.
  - 이를 방지하기 위해 `AGENTS.md`의 핵심 패턴 및 `docs/scheduler.md`에 해당 사실을 명시해야 합니다.
