# KIS OpenAPI 통합

## 범위

KIS 통합은 `app/core/kis_auth.py`의 인증과 `app/core/kis_fetch.py`의 데이터 요청으로 나뉜다. 애플리케이션 코드가 KIS에 요청할 때는 `_do_fetch()`를 직접 호출하지 않고 `async_kis_fetch()`를 사용한다.

## 인증

`kis_devlp.yaml`은 Pydantic `KisConfig`로 검증된다. 현재 운영 모드는 실전투자만 사용한다.

- 앱 키: `my_app`, `my_sec`
- 계좌: 상품 코드에 따라 실전 계좌 선택
- REST URL: `prod`
- WebSocket URL: `ops`
- 토큰 캐시: 루트의 날짜별 `KISYYYYMMDD` 파일

앱 시작 시 `DEBUG=False`면 `auth(force=True)`, `DEBUG=True`면 `auth(force=False)`를 실행한다. OAuth 토큰 발급 요청의 타임아웃은 30초다.

`auth()`는 성공 시에만 정상 반환하며 HTTP·통신·응답 검증·캐시 저장 실패는 `KisAuthError`로 전달한다. 비어 있는 토큰이나 만료된 토큰, 해석할 수 없는 만료 시각은 인증 성공이 아니다. 잘못된 만료 시각에 임의로 24시간을 부여하던 경로를 제거했다. 정상 캐시의 날짜별 파일 형식과 `만료 시각 > 현재 시각` 비교, `force` 정책은 유지한다.

최초 인증은 DB·Queue 생성 전에 완료해야 하며 실패하면 앱이 serving 상태에 진입하지 않는다. 예약 갱신은 실패 로그와 예외로 APScheduler에 실패를 전달한다. 프로세스 종료나 추가 재시도는 하지 않는다. 갱신 실패는 기존 환경·헤더를 바꾸지 않으며 기존 토큰은 원래 만료 시각까지만 사용할 수 있다. 만료 후 `get_kis_env()`는 예외를 내므로 데이터 전송이 발생하지 않는다.

응답 본문, 검증 오류의 입력값, 통신 예외 원문은 인증 오류 메시지에 포함하지 않는다. KIS Code Assistant MCP로 [공식 토큰 발급 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/auth/auth_token/auth_token.py)의 PROD `/oauth2/tokenP` 및 `client_credentials` 요청 경계를 확인했다. 프로젝트의 실패 전파 계약은 [Stage 3·5](testing.md#인증-db-실패-전파-검증)에서 검증하며 공식 예제 자체는 수정하지 않는다.

## 전역 요청 큐

`async_kis_fetch()`는 요청과 응답용 Future를 `asyncio.PriorityQueue`에 넣는다. 단일 consumer가 동기 `requests` 호출을 `asyncio.to_thread()`에서 실행한다.

처리 순서 키는 `(priority, counter, payload)`다.

- 낮은 priority 숫자가 먼저 처리된다.
- counter는 동일 우선순위의 FIFO 순서를 보장한다.
- 각 요청이 끝난 뒤 최소 0.1초를 기다린다. `perf_counter()` deadline까지 남은 시간을 다시 대기해 Windows asyncio 타이머가 일찍 깨워도 최소 간격을 지킨다.
- 일반 데이터 요청의 HTTP 타임아웃은 10초다.

현재 목표 처리율은 약 10 req/s다. KIS의 상한보다 보수적으로 운용하며, 이 지연을 임의로 줄이면 안 된다.

## 워커 수명주기

- 시작: FastAPI lifespan의 `start_q_worker()`
- 지연 시작: 큐가 없는 상태에서 `async_kis_fetch()`가 호출돼도 자동 시작
- 종료: `stop_q_worker()`는 신규 요청을 거부하고 미전송 Future를 취소한다. 이미 시작한 HTTP 요청은 결과 또는 예외로 완료하며, 이후 0.1초 대기까지 끝낸 뒤 종료 신호를 소비한다.
- `start_q_worker()`는 진행 중인 종료가 끝나야 새 큐와 워커를 만든다. 종료 호출자가 취소돼도 공유 종료 태스크는 `asyncio.shield()`로 유지한다.
- 미전송 요청의 Future가 이미 취소됐다면 전송하지 않는다. 종료 후 큐·워커·종료 태스크 참조를 함께 초기화한다.

전송 중 종료·동시 재시작·종료 호출자 취소와 수집기 취소는 [Stage 3·5](testing.md)에서 격리 전송으로 검증한다. 종료는 일반 HTTP 10초 타임아웃과 완료 후 대기를 기다릴 수 있다. 취소 전파와 큐 완료 처리는 [Python asyncio 태스크](https://docs.python.org/3.12/library/asyncio-task.html), [Queue](https://docs.python.org/3.12/library/asyncio-queue.html)의 계약을 따른다.

## 응답 래퍼

`APIResp`는 HTTP 200 여부와 KIS 응답 본문의 `rt_cd == "0"`을 모두 확인한다. JSON 객체는 `DotDict`로 재귀 변환되며, 존재하지 않는 속성은 빈 문자열을 반환한다.

서비스는 다음 순서로 응답을 다룬다.

1. `is_ok()` 확인
2. 실패 시 `get_error_code()` 또는 `get_error_message()` 기록
3. 성공 시 `get_body()`의 TR별 output 읽기

## 호출 규칙

- KIS 요청은 전역 큐를 우회하지 않는다.
- 일반 호출은 `timeout=10`, 인증은 `timeout=30`을 유지한다.
- 요청 로그의 authorization, appkey, appsecret, token 계열 값은 `***`로 마스킹한다. 계좌 전체 값도 기록하지 않는다.
- TR ID와 파라미터는 `open-trading-api/`의 공식 예제를 참고하되 애플리케이션 스키마로 검증한다.
- 투자자 랭킹 `FHPTJ04400000`은 최대 30개 응답만 사용한다.
- 재시도 정책을 추가할 때는 큐 점유, 중복 요청, 장중 지연을 함께 제한한다.
