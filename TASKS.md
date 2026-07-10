# 트레이딩 서버 고도화 작업 내역 (TASKS)

본 문서는 KIS API를 활용한 Zero-Latency Breakout(돌파) 매매 전략 자동화 시스템 구축을 위해 의논된 아키텍처 설계와 앞으로 진행해야 할 구현 태스크들을 명세합니다.

## 1. Database 스키마 고도화 (Schema Updates)
- [ ] **`daily_ohlcv` 테이블에 `amount` (거래대금) 컬럼 추가**
  - 파일: `app/core/database.py`
  - 내용: 현재 일봉 스키마에 거래량(`volume`)만 존재하나, 100원짜리 동전주와 우량주의 거래량 착시를 막고 진정한 '돈의 쏠림'을 파악하기 위해 `amount REAL` 또는 `INTEGER` 컬럼을 DDL에 추가.
- [ ] **`daily_investors` (수급 전용) 테이블 신설**
  - 파일: `app/core/database.py`
  - 내용: 외국인, 기관, 투신, 사모펀드 등의 순매수 대금/수량을 저장할 전용 테이블 생성.
  - 스키마 예시: `ticker`, `date`, `foreign_net`, `inst_net`, `trust_net`, `pe_fund_net`, `retail_net` 등.
- [ ] **`stock_codes` 마스터 테이블 다이어트 (선택)**
  - 내용: 실시간 조인으로 대체 가능한 `prev_vol`(전일거래량)과 전략적 의미가 없는 `capital`(자본금) 컬럼 제거를 통해 정규화 및 I/O 최적화.

## 2. 종목 마스터 심화 필터링 (Master Filtering)
- [ ] **2차 심화 필터링 로직 추가**
  - 파일: `app/tasks/init_stock_codes.py`
  - 내용: 1분봉 차트의 연속성과 슬리피지(Slippage) 방지를 위해 다음의 종목들을 원천 배제.
    - **단기과열 종목 (30분 단일가 매매)**: `단기과열 == "0"`, `단기과열종목구분코드 == "0"`
    - **저유동성 종목 (10분 단일가 매매)**: `저유동성 != "Y"`, `저유동성종목 여부 != "Y"`
    - **투자주의 환기종목 (기관 수급 휩소 방지)**: `(코스닥)투자주의환기종목여부 != "Y"`
- [ ] **마스터 스케줄링(Cron) 확립**
  - 내용: 해당 초기화 코드를 **매일 아침 08:30 (장 시작 전)** 에 덮어쓰기(`replace`)로 무조건 실행되도록 스케줄러에 등록. 당일 갑자기 발생한 거래정지, 단기과열 종목을 스캐너 대상에서 완벽히 증발(Self-Healing)시키기 위함.

## 3. 수급 데이터 파이프라인 개발 (Data Ingestion)
- [ ] **`daily_investors_worker` 구현 및 500일 백필(Backfill)**
  - 내용: KIS API `investor_trade_by_stock_daily` (종목별 투자자매매동향 일별) 엔드포인트를 활용.
  - 특징: 일봉(`daily_ohlcv`)을 수집했던 100개 비동기 큐/워커 아키텍처를 그대로 재활용하여 전 종목(2,500개)의 외인/기관 수급 데이터를 매일 오후 6시 이후에 수집 및 적재.
  - 1차 목표: 기존 일봉과 동일하게 과거 500일 치 수급 데이터를 백필하여 DB에 동기화.

## 4. 분석 및 스캐너 계층 개발 (Analysis & Scanner Layer)
- [ ] **In-Memory 기술적 지표 모듈 생성**
  - 파일: `app/core/indicators.py` (예정)
  - 내용: 이동평균선(MA), 이격도, 매물대(Volume Profile), MACD 등은 **절대 DB에 스케줄링/적재하지 않음**.
  - 구조: 장 시작 전(혹은 매일 자정) DB에서 데이터를 Pandas로 불러와 Vectorization 연산으로 1~2초 만에 전 종목 지표를 계산한 뒤, API 또는 글로벌 상태(State) 메모리에 캐싱. (전략 파라미터 튜닝의 유연성 확보)
- [ ] **Zero-Latency Breakout Scanner 쿼리/로직 작성**
  - 내용: 메모리에 올려둔 지표 캐시 + `stock_codes` + `daily_investors`를 결합하여, API 통신 딜레이 0ms 로 "특정 매물대 돌파 + 외인/투신 연속 매수" 타겟 종목을 실시간으로 색출하는 쿼리 및 필터링 로직 완성.
