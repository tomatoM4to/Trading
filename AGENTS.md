# Agent Instructions

## Scope

KIS OpenAPI로 국내 주식 데이터를 수집하고 로컬 SQLite 기반 스크리너와 차트를 제공한다. 1 OCPU·1GB RAM 환경에서 **데이터 무결성·계좌 안전 → 메모리 생존성 → 호출 제한 → 조회 지연 → 단순성** 순서로 판단한다.

- 한국어로 답한다. 현재 동작의 최종 근거는 테스트 가능한 코드다.
- 작업 전에 이 파일, 관련 문서, 수정할 소스·타입·테스트를 읽는다. 필요한 문서만 읽고 전체 문서를 컨텍스트에 넣지 않는다.
- 기존 사용자 변경을 보존한다. 요청하지 않은 리팩터링·기능·의존성·스키마 변경은 하지 않는다.
- `open-trading-api/`는 외부 참고 서브모듈이다. 명시적 요청 없이 수정하지 않는다.

## Code as Documentation

- 함수·컬럼·상수 목록은 소스에서 확인한다. Markdown에는 책임 경계, 설계 이유, 운영 절차, 검증 근거를 남긴다.
- 코드와 문서가 다르면 충돌을 밝힌다. 버그 수정 요청이 아니라면 코드를 문서에 맞추지 않는다.
- 설계 결정과 대안은 해당 주제 문서에 기록한다. 별도 ADR을 자동 생성하지 않는다.
- 측정값에는 실행 조건과 원본 경로를 붙인다. 과거 측정, 현재 코드, 재검증 필요를 구분하고 원본 CSV를 요약 수치로 대체하지 않는다.

## Safety Boundaries

- 실전투자(PROD) 단일 운영 모드를 유지한다. 모의투자 분기를 임의로 추가하지 않는다.
- 일반 KIS 데이터 요청은 전역 큐를 통과한다. 큐의 `asyncio.sleep(0.1)`, 일반 HTTP 10초·인증 30초 타임아웃을 줄이거나 제거하지 않는다.
- 합의 없이 핵심 테이블, 시스템 가드, 전역 큐, MA 메모리 DB와 keep-alive 연결을 삭제하거나 축소하지 않는다.
- 전 종목 OHLCV를 하나의 Pandas DataFrame으로 적재·병합하지 않는다. SQL 후보 축소와 사전 계산 MA를 우선한다.
- 동적 SQL 값은 바인딩한다. 식별자는 정적 화이트리스트, MA는 `VALID_MA_PERIODS` 검증을 통과시킨다. 기간·임계값·방향·limit의 타입과 범위를 검증한다.
- 운영 데이터에 영향을 주는 통합 검증은 `test_db_var`로 격리한다. SQLite 연결은 context manager만으로 닫힌다고 가정하지 않고 명시적으로 종료한다.
- 데이터 변경 작업의 가드·WAL 체크포인트·날짜/시간 INTEGER 계약을 지킨다. 상세 경계는 [데이터베이스](docs/database.md), [수집](docs/scheduler.md), [KIS](docs/kis-integration.md)에 있다.
- `.env`, `kis_devlp.yaml`, 토큰 캐시, DB 파일을 커밋하지 않는다. 브라우저에 KIS 자격 증명·관리자 키를 전달하지 않는다.
- 관리자 API와 KIS 연동 검증은 부수 효과가 있다. 자동 회귀 테스트와 구분하고 운영 서버에서 임의 실행하지 않는다.

## Context Routing

| 작업 | 먼저 읽을 문서 |
|---|---|
| 구조와 책임 경계 | [architecture](docs/architecture.md) |
| 데이터·메모리 / 수집·GC | [database](docs/database.md), [scheduler](docs/scheduler.md) |
| KIS / HTTP·SSE·스크리너 | [kis-integration](docs/kis-integration.md), [api](docs/api.md), [screener](docs/screener.md) |
| 프론트엔드 | [frontend](docs/frontend.md), [web/AGENTS](web/AGENTS.md) |
| 로컬 설정 / 배포·운영 | [environment](docs/environment.md), [deployment](docs/deployment.md), [operations](docs/operations.md) |
| 성능·검증 기록 | [benchmark](docs/benchmark.md) |

## Completion

검증 명령과 운영 검증의 경계는 [operations](docs/operations.md)를 따른다. 코드 변경은 Ruff·백엔드 회귀 테스트·TypeScript·ESLint·프론트엔드 빌드와 영향 경로의 수동 검증을 확인한다. 문서 변경은 소스 대조, 상대 링크, 명령·측정 출처를 확인한다.

완료 보고에는 변경 파일, 실행한 검사와 결과, 실행하지 못한 검사 및 남은 위험을 구분한다. 일부 검사 통과를 전체 검증 완료로 쓰지 않는다.
