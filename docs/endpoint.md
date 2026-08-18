# 인터페이스 및 엔드포인트 상세 명세서 (API & Endpoint Specs)

본 문서는 FastAPI 프레임워크를 기반으로 구축된 내부 관리용 API 및 외부 클라이언트 호출용(Market) 인터페이스 구조를 정의합니다. KIS OpenAPI와의 통신 결과를 표준화하고, 로컬 DB의 데이터 무결성을 검증하는 데 주 목적이 있습니다.

---

## 1. 글로벌 시스템 방어 (System State Guard)

1 OCPU/1GB RAM 환경의 한계를 극복하기 위해, 백엔드 앱 전역에 `System State Guard`라는 의존성(Dependency)이 주입되어 있습니다.
- **Fail-fast 거절**: 새벽 시간의 지능형 GC, 콜드스타트 데이터 적재, 인메모리 DB 동기화 등 무거운 작업이 돌고 있을 때는 서버를 보호하기 위해 인입되는 모든 API 요청을 즉시 거절합니다.
- **클라이언트 응답**: 대기열(Queue) 없이 즉시 `HTTP 503 (Service Unavailable)` 상태 코드와 함께 `{"detail": "GC 구동 중..."}` 형태의 사유 JSON을 반환합니다.
- **예외 라우터**: 서버 로드밸런서가 인스턴스를 죽었다고 판단하지 않도록, `/health` 라우터만큼은 방어벽을 강제로 통과(bypass)시켜 항상 `200 OK`를 반환하게 설계되었습니다. (단, `/admin` 등 그 외 라우터는 얄짤없이 503을 뱉습니다.)

---

## 2. 통신 객체 래핑 (APIResp Wrapper)

KIS OpenAPI의 JSON 응답은 깊이가 깊고 파편화되어 있습니다. 이를 내부에서 다루기 쉽도록 `APIResp` 객체와 내부 `DotDict` 헬퍼 클래스를 도입하여 점 표기법(Dot-notation)으로 접근할 수 있도록 래핑(Wrapping)합니다.

- **독립성 유지**: `TR_ID`나 엔드포인트 URL 경로 등 API 호출에 필요한 메타 정보는 `app/core/` 하단의 거대한 전역 딕셔너리에 모아두지 않고, **해당 API를 호출하는 서비스 로직이나 라우터 함수 내부에 직접 명시**합니다. 이는 코드를 읽을 때 파편화를 방지하고 결합도를 낮추기 위함입니다.
- **코드 사용 패턴 (예시)**:
  ```python
  # async_kis_fetch를 통해 안전하게 KIS 통신
  resp = await async_kis_fetch(
      api_url=api_url, ptr_id=tr_id, tr_cont="", params=params
  )

  if not resp.is_ok():
      raise HTTPException(
          status_code=400, detail=f"KIS API Error: {resp.get_error_message()}"
      )

  # 응답 본문 추출 (DotDict 변환됨)
  body = resp.get_body()
  ohlcv_data = body.output2  # 점 표기법으로 접근 가능
  ```


---

## 3. 관리자 통합 검증 라우터 (`/admin/test`)
**파일 위치:** `app/routes/admin.py`, `app/services/admin_test_service.py`

배치 스케줄러가 백그라운드에서 적재하는 로직이 100% 무결한지(누락, 동기화 지연 복구 능력 등)를 실제 API 통신을 통해 통합 테스트하는 엔드포인트입니다.

### 3-A. 통합 스케줄러 검증 (`/admin/test/daily_scheduler` & `/admin/test/minute_scheduler`)
- **운영 환경 격리 (Test DB Routing)**:
  - 라이브 운영 DB(`trading.db`)를 건드리지 않기 위해, `test_db_var` (ContextVar)를 사용하여 런타임에 동적으로 `test_trading.db` 파일을 생성하고, 해당 API 요청 스레드에 한해서만 DB 통신을 테스트용 파일로 우회시킵니다.
- **통합 파이프라인 시나리오**:
  1. **콜드스타트 검증**: 무작위 3종목을 텅 빈 테스트 DB에 밀어넣고 1회 스케줄러를 구동하여 정상적으로 초기 적재가 되는지 확인합니다.
  2. **갭필(Gap-fill) 검증**: 수집된 데이터 중 최신 구간을 고의로 잘라내고(DELETE) 스케줄러를 다시 구동하여, 빠진 빈 공간(Gap)만 정확히 인식하고 다시 복구해 내는지 검증합니다.
  3. **디스크 동기화 (Disk Sync) 검증**: 인메모리(Memory) DB에 적재 및 복구된 데이터가 `sync_memory_to_disk()` 함수를 통해 물리적 디스크 파일(`test_trading.db`)에 완벽하게 백업되는지 확인하고, 파일 잠금(Lock) 에러가 없는지 검증합니다.
  4. **1:1 무결성(Integrity) 검증**: 최종적으로 로컬 테스트 DB에 적재된 캔들 값(시/고/저/종/거래량)과 KIS API의 최신 응답값을 실시간으로 비교(Spot Check)하여 100% 일치하는지 확인합니다.
  - 장중(09:00 ~ 15:30) 실시간 검증 시 발생하는 미세한 초 단위 지연(Delay)을 방지하기 위해, 항상 **"DB에 적재된 가장 최신 캔들의 시간"**을 기준으로 잡아 API와 비교함으로써 실시간 통신 노이즈(False Alarm)를 완벽하게 회피합니다.

### 3-B. 라이브 상태 모니터링 (`/admin/live/global-status` & `/admin/live/ticker-status/{ticker}`)
- **운영 환경 직접 조회**:
  - 파괴적인 통합 테스트(`/admin/test`)와 달리 `test_db_var`를 통한 우회 처리를 하지 않고 실제 운영 DB(`trading.db`)를 직접 조회합니다.
- **읽기 전용 (Read-only)**:
  - 파괴적인 작업(수정/삭제) 없이 순수 `SELECT` 및 집계 연산만 수행하여 라이브 DB 락(Lock)을 방지합니다.
- **메타데이터 위주 최적화**:
  - OOM 방지를 위해 실제 수천 개의 캔들 데이터 원본이 아닌, 종목별 데이터 누적 개수, 최초 적재일, 최근 적재일 등의 요약된 상태 정보만을 JSON으로 반환합니다.
  - 거래량이 없어 캔들이 비어있는 소외주의 경우에도 에러가 아닌 정상 상태로 간주하여 처리합니다.

---

## 4. 퍼블릭 마켓 라우터 (`/market`)
**파일 위치:** `app/routes/market.py`, `app/services/market_service.py`

프론트엔드 대시보드(Next.js) 및 차트 뷰어가 호출하는 시세 조회 API입니다. KIS API 실시간 의존 없이 인메모리 SQLite DB를 기반으로 작동합니다.

### 4-A. 차트 및 이동평균선 조회 (`GET /market/chart/{ticker}`)
- **파라미터**:
  - `ticker` (Path, `str`): 종목 코드 (예: `005930`)
  - `days` (Query, `int`, 기본값: 3, 범위: 1~500): 조회 기간 (영업일 기준)
  - `type` (Query, `str`, 기본값: `'minute'`): `'minute'` (분봉) 또는 `'daily'` (일봉)
- **작동 원리**:
  - 로컬 인메모리 DB의 `minute_ohlcv` 또는 `daily_ohlcv` 테이블에서 캔들 시계열을 추출합니다.
  - 동시에 전용 In-Memory MA DB(`minute_ma` 또는 `daily_ma`)와 결합하여 5, 10, 20, 60, 120, 200 이평선 데이터를 완벽히 정렬하여 반환합니다 (참고: ADR-026, ADR-029).
  - 프론트엔드는 1분봉/일봉 원본 데이터를 수신한 뒤 클라이언트 사이드에서 3m, 5m, 15m, 30m, 60m, 주봉, 월봉 등으로 자유롭게 그룹핑(Aggregation)합니다.

### 4-B. 거래대금 상위 랭킹 (`GET /market/screener/top-volume`)
- **파라미터**: 없음 (내부 고정 `limit=30`)
- **작동 원리**:
  - 최근 영업일 기준 거래대금 및 거래량이 가장 높은 상위 30개 종목을 로컬 인메모리 DB에서 즉시 추출하여 반환합니다.

---

## 5. 동적 스크리너 라우터 (`/api/screener`)
**파일 위치:** `app/routes/screener.py`, `app/services/screener_service.py`

사용자가 프론트엔드에서 조합한 다중 기술적 지표(이평선 정배열, 크로스, 수렴, 이격도, 매물대 돌파 등) 및 수급 지표(외국인/기관 순매수)를 실시간으로 평가하여 조건에 부합하는 종목 리스트를 반환하는 핵심 엔진입니다.

### 5-A. 실시간 스크리너 실행 (`POST /api/screener/run`)
- **Request Body**: `ScreenerRequest` (`filters`: Flat List AST, `operations`: `AND`/`OR` 연산자 배열)
- **Response Format**: `StreamingResponse(text/event-stream)` (SSE 방식)
- **작동 원리**:
  - **Zero-Latency In-Memory MA**: 무거운 윈도우 함수(`AVG OVER`)를 일절 사용하지 않고, 부팅/수집 시 사전 계산된 인메모리 테이블(`daily_ma`, `minute_ma`)을 단순 스캔(`ROW_NUMBER() <= duration`)합니다 (참고: ADR-026).
  - **휴리스틱 쿼리 최적화**: Flat AST를 `OR` 기준으로 분기한 후 `AND` 체인 내부를 Big-O 비용 오름차순으로 정렬합니다. KIS 랭킹 API(외인/기관)는 Cost 0으로 최우선 실행되어 종목 모수를 30개로 즉시 축소시킵니다 (참고: ADR-024).
  - **Short-circuit & Parameterized Push-down**: 중간 결과 집합이 빈 집합(`set()`)이 되면 후속 연산을 즉시 중단하며, 축소된 종목 코드는 `WHERE ticker IN (?, ...)` 형태로 안전하게 바인딩됩니다 (참고: ADR-027, ADR-033).
  - **Progressive Feedback**: 필터별 진행률(`progress`)과 최종 리치 데이터(`complete`, 종목명/현재가/거래대금/등락률/다중 지표 점수 `filter_values` 포함)를 SSE 스트림으로 실시간 발행합니다 (참고: ADR-018, ADR-028).

