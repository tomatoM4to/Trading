# FastAPI 인터페이스

## 공통 동작

FastAPI 앱은 모든 경로에 `system_state_guard`를 전역 dependency로 적용한다. 시스템이 무거운 데이터 작업 중이면 `/health`를 제외한 요청에 HTTP 503과 현재 작업 이유를 반환한다.

CORS 허용 origin은 현재 다음 세 곳이다.

- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `https://trading-one-kappa.vercel.app`

## 기본 경로

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 간단한 루트 응답 |
| GET | `/health` | 상태, 현재 시각, 앱 이름. 시스템 가드 우회 |

## 시장 API

### `GET /market/samsung/ohlcv`

KIS API에서 삼성전자 최근 약 100일 일봉을 직접 조회하는 진단용 경로다. 일반 로컬 데이터 조회 원칙의 예외이며 전역 KIS 큐를 사용한다.

### `GET /market/screener/top-volume`

최신 거래일의 거래량 상위 30개 종목을 반환한다.

```json
{
  "date": "20260821",
  "items": [{"ticker": "005930", "name": "삼성전자", "volume": 123456}]
}
```

### `GET /market/chart/{ticker}`

쿼리 파라미터:

- `days`: 1~500, 기본 3
- `type`: `minute` 또는 `daily`, 기본 `minute`

응답은 ticker, 이름과 OHLCV·MA 배열이다. 분봉 응답은 분봉 MA와 해당 시점의 일봉 MA를 함께 제공하고, 일봉 응답은 일봉 MA 필드를 제공한다.

## 스크리너 API

### `POST /api/screener/run`

`ScreenerRequest`를 받아 SSE로 진행 상황과 결과를 전송한다. 상세 필터와 이벤트 계약은 `docs/screener.md`를 따른다.

## 관리자 API

### 통합 검증

- `GET /admin/test/daily_scheduler`
- `GET /admin/test/minute_scheduler`

ContextVar를 이용해 테스트 DB에 라우팅한 뒤 표본 종목의 수집·복구·무결성을 검증한다. GET 요청이지만 외부 KIS 호출과 파일 생성 등 부수 효과가 있다.

### 라이브 상태

- `GET /admin/live/global-status?data_type=daily|minute`
- `GET /admin/live/ticker-status/{ticker}?data_type=daily|minute`

운영 메모리 DB의 적재 현황을 읽는다.

### 운영 작업

- `POST /admin/action/gc`

지능형 GC를 즉시 실행한다. 실행 중 일반 API가 503으로 차단되며 완료 후 디스크 동기화가 수행된다.

## 보안 경계

모든 `/admin/*` 경로는 `X-Admin-Key` 헤더를 요구하며 서버의 `ADMIN_API_KEY`와 상수 시간 비교한다. 키가 없거나 다르면 401, 서버 키가 설정되지 않았으면 fail-closed로 503을 반환한다. Nginx는 `/docs`와 `/redoc`을 계속 프록시하므로 API 문서 노출은 별도 네트워크 정책이 필요하다.

## 오류 규칙

- Pydantic 요청 오류: HTTP 422
- 명시적 쿼리 파라미터 오류: HTTP 400
- 시스템 가드: HTTP 503
- 스크리너 실행 중 오류: HTTP 200 SSE 연결 안의 `error` 이벤트일 수 있음
- KIS 오류: 호출 경로에 따라 HTTP 400 또는 빈 필터 결과
