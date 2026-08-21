# 시스템 아키텍처

## 목적과 제약

Trading Server & Dashboard는 KIS OpenAPI에서 국내 종목 데이터를 수집하고, 로컬 데이터 기반 스크리너와 차트를 제공한다. 운영 환경은 1 OCPU, 1GB RAM의 단일 서버이므로 분산 시스템보다 작은 메모리 점유, 예측 가능한 실패, 단순한 복구를 우선한다.

## 런타임 구성

```text
KIS OpenAPI
  └─ 인증 및 전역 PriorityQueue
       └─ 수집 태스크 / 관리자 검증
            ├─ Shared In-Memory SQLite (주 데이터)
            │    └─ trading.db로 주기적 backup
            └─ Shared In-Memory MA DB
                 ├─ daily_ma
                 └─ minute_ma

FastAPI
  ├─ /market
  ├─ /api/screener
  ├─ /admin
  └─ /health
       ↑
Next.js 대시보드
```

## 백엔드 모듈 경계

| 경로 | 책임 |
|---|---|
| `app/main.py` | FastAPI 생성, lifespan, CORS, 라우터 조립 |
| `app/core/database.py` | DB 경로 결정, 연결 생성, 스키마, 메모리/디스크 동기화 |
| `app/core/kis_auth.py` | KIS 설정 로드와 OAuth 토큰 발급·캐시 |
| `app/core/kis_fetch.py` | 모든 KIS 요청을 직렬화하는 전역 우선순위 큐 |
| `app/core/scheduler.py` | APScheduler 작업 등록과 실행 조정 |
| `app/core/bootstrap.py` | OHLCV 기반 MA DB 재구축과 초기 데이터 파이프라인 |
| `app/core/state.py` | 무거운 작업 중 API를 막는 프로세스 전역 상태 |
| `app/tasks/` | 종목 마스터, 일봉, 분봉 수집 구현 |
| `app/services/` | API가 사용하는 조회·스크리너·관리자 유스케이스 |
| `app/routes/` | HTTP 경계와 요청 기본 검증 |
| `app/schemas/` | Pydantic 요청·응답 계약 |

## 시작 순서

`app/main.py`의 lifespan은 다음 순서를 따른다.

1. `.env`를 로드하고 로깅을 초기화한다.
2. 디스크 DB가 있으면 Shared In-Memory DB로 복원하고 스키마를 보장한다.
3. KIS 전역 요청 워커를 시작한다.
4. `DEBUG` 값에 따라 토큰을 재발급하거나 캐시를 재사용한다.
5. `SCHED=True`면 `SystemScheduler`와 부트스트랩 파이프라인을 시작한다.
6. `SCHED=False`면 기존 OHLCV로 MA 메모리 DB만 재구축한다.

부트스트랩과 MA 재구축은 백그라운드 태스크다. 해당 작업은 내부에서 `system_state.acquire()`를 사용하므로 작업 중 `/health` 외 요청은 503을 받을 수 있다.

## 종료 순서

1. KIS 요청 워커를 취소하고 종료를 기다린다.
2. 스케줄러가 시작돼 있었다면 종료한다.

현재 lifespan이 부트스트랩 태스크의 참조를 보관하거나 종료를 기다리지는 않는다. 이 동작을 바꾸려면 shutdown 시 데이터 일관성과 취소 정책을 함께 설계해야 한다.

## 시스템 상태 가드

`SystemState`는 스레드 안전한 중첩 카운터다. 첫 `acquire()`에서 unavailable로 전환하고 마지막 컨텍스트가 끝날 때 available로 복구한다. FastAPI 전역 dependency인 `system_state_guard`가 상태를 읽어 503을 반환한다.

- 우회 경로: `/health`
- 차단 경로: 그 외 모든 FastAPI 경로
- 사용 작업: 부트스트랩 MA 재구축, 마스터 동기화, GC, 정규 일봉 업데이트

## 외부 서브모듈

`open-trading-api/`는 KIS 공식 저장소를 연결한 Git submodule이다. 인증 및 API 파라미터의 참고 자료이며 애플리케이션 런타임 소유 코드가 아니다.
