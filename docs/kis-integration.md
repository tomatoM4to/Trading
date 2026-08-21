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

## 전역 요청 큐

`async_kis_fetch()`는 요청과 응답용 Future를 `asyncio.PriorityQueue`에 넣는다. 단일 consumer가 동기 `requests` 호출을 `asyncio.to_thread()`에서 실행한다.

처리 순서 키는 `(priority, counter, payload)`다.

- 낮은 priority 숫자가 먼저 처리된다.
- counter는 동일 우선순위의 FIFO 순서를 보장한다.
- 각 요청이 끝난 뒤 반드시 `asyncio.sleep(0.1)`한다.
- 일반 데이터 요청의 HTTP 타임아웃은 10초다.

현재 목표 처리율은 약 10 req/s다. KIS의 상한보다 보수적으로 운용하며, 이 지연을 임의로 줄이면 안 된다.

## 워커 수명주기

- 시작: FastAPI lifespan의 `start_q_worker()`
- 지연 시작: 큐가 없는 상태에서 `async_kis_fetch()`가 호출돼도 자동 시작
- 종료: lifespan의 `stop_q_worker()`가 태스크를 cancel하고 종료를 기다림

## 응답 래퍼

`APIResp`는 HTTP 200 여부와 KIS 응답 본문의 `rt_cd == "0"`을 모두 확인한다. JSON 객체는 `DotDict`로 재귀 변환되며, 존재하지 않는 속성은 빈 문자열을 반환한다.

서비스는 다음 순서로 응답을 다룬다.

1. `is_ok()` 확인
2. 실패 시 `get_error_code()` 또는 `get_error_message()` 기록
3. 성공 시 `get_body()`의 TR별 output 읽기

## 호출 규칙

- KIS 요청은 전역 큐를 우회하지 않는다.
- 일반 호출은 `timeout=10`, 인증은 `timeout=30`을 유지한다.
- 로그에 앱 시크릿, 토큰, 계좌 전체 값이 남지 않도록 한다.
- TR ID와 파라미터는 `open-trading-api/`의 공식 예제를 참고하되 애플리케이션 스키마로 검증한다.
- 투자자 랭킹 `FHPTJ04400000`은 최대 30개 응답만 사용한다.
- 재시도 정책을 추가할 때는 큐 점유, 중복 요청, 장중 지연을 함께 제한한다.
