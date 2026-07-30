## Task 1: Create Screener Schemas
**Description:** 파이프라인 엔진이 처리할 필터 리스트와 논리 연산자(AND/OR)를 정의하는 Pydantic 스키마 작성
**Acceptance criteria:**
- [x] `app/schemas/screener.py` 파일 생성
- [x] 여러 개의 조건을 담는 리스트(filters)와 일괄 연산자(operation: AND/OR) 정의
- [x] MA Uptrend 필터에 필요한 파라미터(이평선 종류 목록, N일 등) 정의

## Task 2: Implement Screener Orchestrator
**Description:** 여러 조건(필터)들의 결과를 순차적으로 받아 일괄 Set(교집합/합집합) 연산을 수행하는 뼈대 엔진 생성
**Acceptance criteria:**
- [x] `app/services/screener_service.py` 생성
- [x] 각 필터 모듈을 호출하여 `Set[str]`을 구하고, 이를 `&`(AND) 또는 `|`(OR)로 일괄 집계하는 로직 구현

## Task 3: Implement MA Uptrend Filter Logic
**Description:** 선택된 이평선들이 N일간 연속으로 기울기가 양수(증가)인지 확인하는 SQLite 기반 로직 구현
**Acceptance criteria:**
- [x] SQLite 윈도우 함수를 사용해 메모리 효율적으로 조건을 판별하는 쿼리 작성
- [x] 쿼리 결과를 `Set[str]` 형태로 엔진에 반환

## Task 4: Create Screener Route Endpoint
**Description:** 클라이언트 요청을 처리할 API 엔드포인트 등록
**Acceptance criteria:**
- [x] `app/routes/screener.py` 엔드포인트 생성 (`POST /screener/run`)
- [x] `app/main.py`에 라우터 등록
- [x] API 호출 테스트 통과
