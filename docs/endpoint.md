# 인터페이스 및 엔드포인트 상세 명세서 (API & Endpoint Specs)

본 문서는 FastAPI 프레임워크를 기반으로 구축된 내부 관리용 API 및 외부 클라이언트 호출용(Market) 인터페이스 구조를 정의합니다. KIS OpenAPI와의 통신 결과를 표준화하고, 로컬 DB의 데이터 무결성을 검증하는 데 주 목적이 있습니다.

---

## 1. 통신 객체 래핑 (APIResp Wrapper)

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

## 2. 관리자 통합 검증 라우터 (`/admin/test`)
**파일 위치:** `app/routes/admin.py`, `app/services/admin_test_service.py`

배치 스케줄러가 백그라운드에서 적재하는 로직이 100% 무결한지(누락, 동기화 지연 복구 능력 등)를 실제 API 통신을 통해 통합 테스트하는 엔드포인트입니다.

### 2-A. 통합 스케줄러 검증 (`/admin/test/daily_scheduler` & `/admin/test/minute_scheduler`)
- **운영 환경 격리 (Test DB Routing)**:
  - 라이브 운영 DB(`trading.db`)를 건드리지 않기 위해, `test_db_var` (ContextVar)를 사용하여 런타임에 동적으로 `test_trading.db` 파일을 생성하고, 해당 API 요청 스레드에 한해서만 DB 통신을 테스트용 파일로 우회시킵니다.
- **통합 파이프라인 시나리오**:
  1. **콜드스타트 검증**: 무작위 3종목을 텅 빈 테스트 DB에 밀어넣고 1회 스케줄러를 구동하여 정상적으로 초기 적재가 되는지 확인합니다.
  2. **갭필(Gap-fill) 검증**: 수집된 데이터 중 최신 구간을 고의로 잘라내고(DELETE) 스케줄러를 다시 구동하여, 빠진 빈 공간(Gap)만 정확히 인식하고 다시 복구해 내는지 검증합니다.
  3. **디스크 동기화 (Disk Sync) 검증**: 인메모리(Memory) DB에 적재 및 복구된 데이터가 `sync_memory_to_disk()` 함수를 통해 물리적 디스크 파일(`test_trading.db`)에 완벽하게 백업되는지 확인하고, 파일 잠금(Lock) 에러가 없는지 검증합니다.
  4. **1:1 무결성(Integrity) 검증**: 최종적으로 로컬 테스트 DB에 적재된 캔들 값(시/고/저/종/거래량)과 KIS API의 최신 응답값을 실시간으로 비교(Spot Check)하여 100% 일치하는지 확인합니다.
  - 장중(09:00 ~ 15:30) 실시간 검증 시 발생하는 미세한 초 단위 지연(Delay)을 방지하기 위해, 항상 **"DB에 적재된 가장 최신 캔들의 시간"**을 기준으로 잡아 API와 비교함으로써 실시간 통신 노이즈(False Alarm)를 완벽하게 회피합니다.

### 2-B. 라이브 상태 모니터링 (`/admin/live/global-status` & `/admin/live/ticker-status/{ticker}`)
- **운영 환경 직접 조회**:
  - 파괴적인 통합 테스트(`/admin/test`)와 달리 `test_db_var`를 통한 우회 처리를 하지 않고 실제 운영 DB(`trading.db`)를 직접 조회합니다.
- **읽기 전용 (Read-only)**:
  - 파괴적인 작업(수정/삭제) 없이 순수 `SELECT` 및 집계 연산만 수행하여 라이브 DB 락(Lock)을 방지합니다.
- **메타데이터 위주 최적화**:
  - OOM 방지를 위해 실제 수천 개의 캔들 데이터 원본이 아닌, 종목별 데이터 누적 개수, 최초 적재일, 최근 적재일 등의 요약된 상태 정보만을 JSON으로 반환합니다.
  - 거래량이 없어 캔들이 비어있는 소외주의 경우에도 에러가 아닌 정상 상태로 간주하여 처리합니다.

---

## 3. 퍼블릭 마켓 라우터 (`/market`)
**파일 위치:** `app/routes/market.py`

프론트엔드 대시보드(Next.js 예정) 혹은 내부 트레이딩 봇이 판단을 내리기 위해 호출하는 API입니다.

### 3-A. Zero-Latency 시세 및 스크리너 조회 (`/screener/minute-breakout`)
- **작동 원리**:
  - KIS API 서버를 거치지 않고 오직 로컬 `trading.db`의 `minute_ohlcv` 테이블만을 조회합니다.
  - 1GB RAM 환경에서 Pandas로 수천 종목을 병합(`Merge`)하는 메모리 폭발을 막기 위해, **SQLite의 윈도우 함수(`AVG() OVER (PARTITION BY ticker ORDER BY date, time)`)** 등을 적극 활용하여 이동평균선 계산과 조건 필터링을 DB 엔진단에서 처리합니다.
  - 이를 통해 특정 조건(예: 거래대금 폭발, 특정 이평선 돌파)을 만족하는 주도주 리스트(Hotlist)를 수십 밀리초 내로 즉각 반환합니다.

### 3-B. (추후 확장을 위한) 실시간 스트리밍
- 추후 프론트엔드(Next.js / React Native) 대시보드 구성을 위해 WebSocket이나 SSE(Server-Sent Events)를 통해 스크리너 결과를 실시간 알림 형태로 Push하는 기능이 추가될 예정입니다.
