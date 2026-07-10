# Spec: Application Bootstrap Pipeline (자동 초기화 파이프라인)

## Objective
빈 DB로 서버를 시작했을 때, 여러 스케줄러(일봉, 분봉, 수급 등)가 동시에 API를 호출하여 Rate Limit을 초과하거나 엉키는 문제를 방지합니다. 
FastAPI 서버가 켜지면 **백그라운드에서 순차적으로(Sequentially) 비어있는 DB를 감지하고 채우는 파이프라인**을 구축합니다.

## Architecture & Workflow
FastAPI의 `lifespan` 훅에서 서버 응답을 블로킹하지 않도록 `asyncio.create_task()`로 백그라운드 부트스트랩을 던집니다.
부트스트랩 파이프라인의 순서는 다음과 같습니다:

1. **Step 1: 마스터 데이터 (stock_codes)**
   - `SELECT COUNT(*) FROM stock_codes` 확인.
   - 0개면 `init_stock_codes.py` 실행 후 완료까지 대기(`await`).
2. **Step 2: 일봉 데이터 (daily_ohlcv)**
   - `SELECT COUNT(*) FROM daily_ohlcv` 확인.
   - 100개 미만이면 `run_daily_ohlcv_scheduler()` 실행 후 완료까지 대기(`await`).
3. **Step 3: 분봉 데이터 (minute_ohlcv)** *(추후 연동)*
   - 일봉 완료 후 검사 및 실행.
4. **Step 4: 수급 데이터 (daily_investors)** *(추후 연동)*
   - 분봉 완료 후 검사 및 실행.

## Success Criteria
- [ ] 서버 기동 시 DB가 비어있으면 마스터 -> 일봉 -> (분봉) 순으로 차례대로 적재된다.
- [ ] 파이프라인이 도는 중에도 FastAPI 서버는 정상적으로 켜져서 API(`/admin/...` 등) 응답이 가능하다.
- [ ] 이미 데이터가 채워져 있는 경우(예: 서버 단순 재시작), 각 Step은 `COUNT(*)` 검사만 하고 0.01초 만에 즉시 통과(Skip)한다.

## Boundaries
- Always: KIS API Rate Limit을 위해 각 Step은 반드시 `await`로 완전 종료를 확인한 뒤 다음 Step으로 넘어간다.
- Ask first: FastAPI `main.py`의 구조를 크게 변경하는 경우.
