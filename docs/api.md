# FastAPI 인터페이스

## Current Decision

HTTP 경계는 입력 검증·인증·시스템 가드를 담당하고, 조회·수집 로직은 서비스에 둔다. 개별 필드의 최신 타입·기본값은 [routes](../app/routes/)와 [schemas](../app/schemas/)가 기준이다. 실행 중인 앱의 `/docs`도 같은 코드에서 생성된다.

## Route Map

| 경로 | 책임·주의사항 | 구현 |
|---|---|---|
| `GET /`, `GET /health` | 루트 응답·프로세스 상태. `/health`만 시스템 가드 우회 | [main](../app/main.py) |
| `GET /market/samsung/ohlcv` | KIS 직접 조회 진단. 일반 로컬 조회의 예외이며 전역 큐 사용 | [market](../app/routes/market.py) |
| `GET /market/screener/top-volume` | 최신 거래일 거래량 상위 종목 조회 | [market](../app/routes/market.py) |
| `GET /market/chart/{ticker}` | 로컬 OHLCV·MA 차트 조회 | [market](../app/routes/market.py), [service](../app/services/market_service.py) |
| `POST /api/screener/run` | AST를 실행하고 SSE 전송 | [screener](../app/routes/screener.py), [이벤트 계약](screener.md#sse-계약) |
| `GET /admin/live/global-status`, `/admin/live/ticker-status/{ticker}` | 디스크 OHLCV의 적재 날짜·행 수 확인 | [admin](../app/routes/admin.py), [live service](../app/services/admin_live_service.py) |
| `GET /admin/test/daily_scheduler`, `/admin/test/minute_scheduler` | 테스트 DB를 만드는 실제 KIS 통합 검증. GET에도 부수 효과 존재 | [admin](../app/routes/admin.py), [test service](../app/services/admin_test_service.py) |
| `POST /admin/action/gc` | 데이터 삭제와 WAL 체크포인트를 포함하는 운영 작업 | [admin](../app/routes/admin.py), [scheduler](../app/core/scheduler.py) |

## Safety Boundaries

- 전역 `system_state_guard`는 데이터 변경 작업 중 `/health` 외 요청을 503으로 차단한다. `/health`의 성공은 데이터 준비 완료를 뜻하지 않는다.
- 모든 `/admin/*`는 `X-Admin-Key`를 요구한다. 서버 `ADMIN_API_KEY`가 없으면 503, 요청 키가 없거나 다르면 401이다. 비교는 상수 시간 방식이다.
- CORS 허용 origin은 [main.py](../app/main.py)에서 관리한다. CORS를 관리자 인증으로 취급하지 않는다.
- `/docs`와 `/redoc`은 Nginx를 통해 노출된다. 네트워크 제한 등 운영 정책은 [배포](deployment.md)와 [운영](operations.md)을 따른다.
- 관리자 통합 검증과 GC는 단순 읽기가 아니다. 자동 테스트 명령에 섞지 않는다.

## Error Contract

| 상황 | 응답 |
|---|---|
| Pydantic 요청 오류 | HTTP 422 |
| 명시적 쿼리 검증 오류 | HTTP 400 |
| 시스템 가드·관리자 키 미설정 | HTTP 503 |
| 관리자 인증 실패 | HTTP 401 |
| SSE 실행 중 오류 | HTTP 200 스트림 안의 `error` 이벤트 가능 |
| KIS 오류 | 호출 경로에 따라 HTTP 400 또는 빈 필터 결과 |

SSE 소비자는 HTTP 성공만으로 계산 완료를 판단하지 않는다. [스크리너 계약](screener.md)과 [프론트엔드 처리](frontend.md)를 함께 확인한다.
