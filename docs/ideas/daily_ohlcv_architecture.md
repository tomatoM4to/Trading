# Daily OHLCV & Screener Architecture

## Problem Statement
How Might We (HMW): 1GB 메모리의 제약 상황에서, KIS API의 Rate Limit을 방어하며 **순수 OHLCV 데이터만으로 200일선 등 다중 이평선을 실시간(Zero-latency)으로 계산하고**, 외인/기관 매수량 등의 보조 지표를 효율적으로 스크리닝할 수 있을까?

## Recommended Direction
**1. 순수 원본(Raw) 데이터 유지 및 SQLite 위임 (Zero-Python-Memory)**
`daily_ohlcv` 테이블 스키마를 현재 상태(OHLCV + 거래량)로 순수하게 유지합니다. Python(Pandas)으로 이평선을 사전 계산하여 메모리를 점유하는 대신, SQLite의 강력한 윈도우 함수(`AVG(close) OVER (...)`)를 사용하여 사용자가 스크리닝을 요청할 때(On-demand) 쿼리단에서 즉시 계산합니다.

**2. 보조 지표 분리 (Separation of Concerns)**
Daily OHLCV API에는 외인/기관 수급 데이터가 전혀 포함되어 있지 않습니다. 따라서 이를 OHLCV 수집 파이프라인에 억지로 끼워 넣지 않고, 별도의 `investor_trade_by_stock_daily` (종목별 투자자매매동향) API를 호출하는 독립된 워커를 구성하거나, 최종 필터링을 통과한 소수의 종목에 대해서만 On-demand로 수급 지표를 찔러서 가져옵니다.

## Key Assumptions to Validate
- [ ] SQLite의 `AVG OVER` 연산이 2,400개 종목 x 500일(약 120만 로우) 데이터를 대상으로 5분 내외에 처리될 수 있는가? (인덱스 최적화 필요)
- [ ] 사용자 5명 내외가 동시에 On-demand 스크리닝을 요청했을 때 CPU 스파이크가 서버(1 OCPU)를 다운시키지 않는가?
- [ ] 외인/기관 매수량 데이터가 Zero-latency 스크리닝의 '선행 조건'이 아닌 '후행 조건(통과된 종목에 한해 보여주는 정보)'으로 작용해도 사용자의 전략에 무리가 없는가?

## MVP Scope
- **In:** 기존 `daily_ohlcv_scheduler.py` 무수정 그대로 사용 (현재 스키마 완벽함).
- **In:** 스크리너 API(`/screener`) 호출 시 내부적으로 `AVG(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN N PRECEDING AND CURRENT ROW)` 형태의 쿼리를 동적 생성.
- **Out:** 외인/기관 매수량 및 매물대 지표의 실시간 DB 적재 (일단 제외하고 후순위로 미룸).

## Not Doing (and Why)
- **Pandas를 이용한 이평선 사전 계산 및 DB 적재:** 2,400개 종목의 500일치 데이터를 Pandas로 끌어와서 1~200일선을 모두 계산하고 다시 넣는 것은 1GB 램 환경에서 OOM(Out of Memory)을 유발할 위험이 큽니다.
- **일봉 통신에 수급 데이터 병합:** KIS API 구조상 일봉 통신(FHKST03010100)에는 수급 데이터가 없습니다. 이를 합치려면 API 호출이 2배로 늘어나 Rate Limit 큐가 버티지 못합니다.

## Open Questions
- 기관/외국인 매수량을 "스크리닝 조건(WHERE절)"으로 꼭 써야 한다면, 이 데이터를 스케줄러로 매일 수집하는 별도의 테이블(`daily_investor_trend`)을 만들어야 할까요? 아니면 1차 필터링을 통과한 종목에 대해서만 실시간으로 API를 호출해 클라이언트에 던져주면 될까요?
