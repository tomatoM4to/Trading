# On-Demand Screener & Minute Scheduler Pipeline

## Problem Statement
How Might We (어떻게 하면) 1GB RAM 및 API 초당 20회 제한이라는 극단적인 제약 환경 속에서, 2,400개 전 종목의 복잡한 조건(다중 이평선, 매물대, 재무제표, 수급)을 외부 API 지연(Zero-latency) 없이 실시간에 가깝게 필터링하여 유저(1~5인)에게 제공할 수 있을까?

## Recommended Direction
**"Background Data Pump + Chunk 기반 로컬 DB 스캐너 + Client-side 매물대 오프로딩"**

이 아키텍처는 서버와 클라이언트의 역할을 극단적으로 분리하여 제약을 극복합니다.
1. **Minute Scheduler (Data Pump):** 서버는 장 중(09:00~16:00) 무한 루프를 돌며 큐(Queue)를 2,400개로 리필(1초 대기)하고, 누락된 데이터는 최대 15회 백필, 실패 시 3회 재시도하여 로컬 SQLite DB를 최신화하는 작업에만 100% 집중합니다.
2. **On-Demand Local Screener:** 유저가 검색 버튼을 누르면 서버는 KIS API 통신 없이 로컬 DB만을 조회하여 조건(재무, MAs, 수급 등)을 필터링합니다. OOM 방지를 위해 100개 종목씩 청크 단위로 끊어 연산하며 1~5분 내에 매칭된 소수 종목 리스트를 반환합니다.
3. **Client-Side Offloading:** 가장 무거운 '매물대(Volume Profile)' 연산 및 차트 시각화는 서버가 아닌 클라이언트(앱)로 위임합니다. 검색된 소수 종목의 Raw Data를 Lazy Load로 넘겨받아 클라이언트가 연산합니다.

## Key Assumptions to Validate
- [ ] **메모리(OOM) 방어:** 1GB RAM 환경에서 Pandas로 100개씩 청크 연산을 수행할 때, 메모리 릴리즈(GC)가 정상 작동하여 서버가 뻗지 않는가?
- [ ] **마스터 파일 데이터 적재:** 매일 아침 실행되는 `kis_kospi_code_mst.py`의 풍부한 재무/위험 지표(ROE, 영업이익, 단기과열 등)가 SQLite `stock_codes` 테이블에 올바르게 삽입 및 업데이트되는가?
- [ ] **클라이언트 연산력:** 서버가 던져준 종목의 분봉 Raw Data를 바탕으로 클라이언트 기기가 매물대를 버벅임 없이 그려낼 수 있는가?

## MVP Scope
- **서버 측:** 
  - `kis_fetch` 속도(20/s)에 맞춘 Q 기반 Minute Scheduler 무한 루프 구현 (리필 시 1초 대기, 15회 백필, 3회 재시도 로직).
  - 아침 부트스트랩 시 KIS 마스터 파일의 재무/위험 지표를 파싱하여 DB 테이블(`stock_codes`) 확장 적용.
  - API 엔드포인트 `/screener` 개발 (로컬 DB만을 이용한 Chunk 기반 필터링 수행).
- **클라이언트 측:**
  - 서버에서 받은 결과 리스트 표출 및 개별 종목 탭 시 매물대 로컬 연산/렌더링 구현.

## Not Doing (and Why)
- **서버 측 매물대 계산** — 2,400개 종목의 장기 분봉을 서버 메모리에 올려 구간별로 집계하는 것은 1GB RAM에서 절대 불가능하므로 배제.
- **실시간(Real-time) 자동 검색 스캐너** — 스케줄러가 백그라운드에서 매 분 조건 검색을 돌려 푸시 알림을 주는 방식은 메모리와 CPU를 지속 점유하므로 배제 (유저 트리거 기반 On-demand 방식 채택).
- **단일 거대 DataFrame 연산** — 조건 검색 시 `SELECT * FROM ohlcv`를 한 번에 올리는 행위 배제 (반드시 Chunk 분할 연산).

## Open Questions
- 분봉 데이터를 며칠 치(예: 3.5일) 확보할지 정해졌지만, 다중 이평선(200, 100, 30 등)을 검색하려면 '일봉(daily)' 데이터와 '분봉(minute)' 데이터를 어느 시점에서 결합하여 스크리너 조건으로 연산할 것인가?
