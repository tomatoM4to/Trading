# 시스템 아키텍처

## 목적과 제약

Trading Server & Dashboard는 KIS OpenAPI에서 국내 종목 데이터를 수집하고, 로컬 데이터 기반 스크리너와 차트를 제공한다. 운영 환경은 1 OCPU, 1GB RAM의 단일 서버이므로 분산 시스템보다 작은 메모리 점유, 예측 가능한 실패, 단순한 복구를 우선한다.

`trading.db`는 외부 원본을 대신하는 영구 원장이 아니라 KIS 데이터로 재구축 가능한 로컬 정본이다. 장애 시 DB를 비우고 다시 수집할 수 있다는 단순성을 유지하되, 정상 운영 중에는 외부 API 장애가 조회 경로로 전파되지 않도록 디스크 데이터를 우선 사용한다.

## 런타임 구성

```text
KIS OpenAPI
  └─ 인증 및 전역 PriorityQueue
       └─ 수집 태스크 / 관리자 검증
            ├─ SQLite trading.db (종목 마스터·OHLCV 정본, WAL)
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
| `app/core/database.py` | 디스크 DB 연결·스키마·WAL 체크포인트와 MA 메모리 DB 수명주기 |
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
2. 디스크 DB에 직접 연결해 WAL을 적용하고 주 데이터 스키마를 보장한 뒤 MA Shared In-Memory DB를 준비한다.
3. KIS 전역 요청 워커를 시작한다.
4. `DEBUG` 값에 따라 토큰을 재발급하거나 캐시를 재사용한다.
5. `SCHED=True`면 `SystemScheduler`와 부트스트랩 파이프라인을 시작한다.
6. `SCHED=False`면 기존 OHLCV로 MA 메모리 DB만 재구축한다.

부트스트랩과 MA 재구축은 백그라운드 태스크다. 해당 작업은 내부에서 `system_state.acquire()`를 사용하므로 작업 중 `/health` 외 요청은 503을 받을 수 있다.

## 메모리 구조 선택

이전에는 약 202MiB의 OHLCV DB 전체와 사전 계산 MA를 함께 Shared In-Memory SQLite에 유지했다. 1GB 서버에서는 같은 OHLCV를 디스크와 애플리케이션 메모리에 중복 보유해 SQLite 임시 작업, Pandas, Python과 OS 페이지 캐시의 여유를 줄였다.

현재 구조는 전 종목 필터에서 반복 사용하는 MA만 메모리에 두고, OHLCV는 WAL 기반 디스크 SQLite와 OS 페이지 캐시에 맡긴다. 사전 계산 MA를 없애면 전 종목 윈도 계산 비용이 다시 커지고, Go 재작성은 현재 CPU보다 데이터 중복이 우선 병목이므로 선택하지 않았다. 메모리 증설은 구조적 중복을 제거한 뒤에도 부족할 때 사용하는 운영 대안이다.

동일한 약 202MiB DB의 로컬 단일 실행에서는 디스크 정본 사용 시 거래량 돌파 필터가 일봉 1개월 `0.510초 → 0.532초`, 분봉 4시간 `3.332초 → 3.463초`로 약 4% 느렸다. OS 페이지 캐시와 측정 노이즈가 포함된 기준선이므로 운영 환경에서는 RSS와 응답시간을 다시 측정한다.

## 종료 순서

1. 스케줄러가 시작돼 있었다면 새 작업 등록을 중단한다.
2. lifespan이 소유한 부트스트랩 또는 MA 재구축 태스크를 취소하고 종료를 기다린다.
3. KIS 요청 워커를 취소하고 종료를 기다린다.

## 시스템 상태 가드

`SystemState`는 스레드 안전한 중첩 카운터다. 첫 `acquire()`에서 unavailable로 전환하고 마지막 컨텍스트가 끝날 때 available로 복구한다. FastAPI 전역 dependency인 `system_state_guard`가 상태를 읽어 503을 반환한다.

- 우회 경로: `/health`
- 차단 경로: 그 외 모든 FastAPI 경로
- 사용 작업: 부트스트랩 MA 재구축, 마스터 동기화, GC, 정규 일봉 업데이트

## 외부 서브모듈

`open-trading-api/`는 KIS 공식 저장소를 연결한 Git submodule이다. 인증 및 API 파라미터의 참고 자료이며 애플리케이션 런타임 소유 코드가 아니다.
