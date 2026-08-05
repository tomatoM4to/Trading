# 스크리너 벤치마크 및 부하 테스트 (Screener Benchmark)

## 1. 개요
`scripts/benchmark_screener.py` 스크립트는 Trading Server의 핵심인 **스크리너 엔진(Screener Engine)**의 실시간 성능과 부하 처리 능력을 측정하기 위해 작성되었습니다. 

본 벤치마크는 2,400개 전 종목을 대상으로 복잡한 SQLite Push-down 윈도우 함수 쿼리(이평선 정배열, 크로스, 밀집 등)가 디스크 I/O 및 1GB RAM 환경(Oracle Cloud)에서 어느 정도의 지연 시간(Latency)을 발생시키는지 추적합니다.

## 2. 벤치마크 시나리오 구성
벤치마크는 크게 가벼운 단일 연산(Light)과 극단적인 다중 조건(Heavy) 그룹으로 나뉩니다.

### ☀️ Light Scenarios (단일/단순 필터)
1. **Light 1 (Daily Cross)**: 일봉 기준 단기/장기 이평선 크로스 단일 검사 (`ma_daily_5` 상향 돌파 `ma_daily_20`).
2. **Light 2 (Minute Cross)**: 분봉 기준 단기/장기 이평선 크로스 단일 검사.
3. **Light 3 (Daily Alignment)**: 3개 일봉 이평선(`ma_daily_5, 20, 60`)의 정배열 상태 유지 검사.
4. **Light 4 (Minute Convergence Point)**: 분봉 기준 2개 이평선의 단기 밀집 지점 발생 여부 검사.
5. **Light 5 (Daily Alignment + Foreign Buy Rank)**: 정배열 검사와 KIS 외부 수급 API(외국인 순매수 상위)를 `AND` 연산으로 조합.

### ⛈️ Heavy Scenarios (극한 스트레스 테스트)
1. **Heavy 1 (Daily Deep Window)**: 5개 이평선 정배열 + 수렴 횡보 + 크로스 + 외부 수급(외인/기관)을 동시에 만족하는 종목 찾기.
2. **Heavy 2 (Minute Stress Test)**: 분봉 데이터(약 460만 건)를 대상으로 5개 이평선 정배열 및 밀집 등을 장기간(10 캔들 이상) 추적.
3. **Heavy 3 (Mixed Timeframes Combo)**: 일봉과 분봉 쿼리를 하나의 파이프라인에서 섞어서 교집합(`AND`) 처리 시의 성능 측정.
4. **Heavy 4 (Extreme Window Functions)**: 다수의 이평선과 긴 탐색 기간(`duration: 15`)을 주입하여 SQLite 임시 테이블 생성 및 정렬 오버헤드 극대화.
5. **Heavy 5 (Full Minute DB Scan)**: 전체 분봉 DB에 대해 가능한 모든 무거운 연산을 동시에 쏟아붓는 최고 부하 테스트.

## 3. 실행 방법

벤치마크 스크립트는 `uv` 환경 또는 파이썬 가상환경에서 `requests` 라이브러리를 통해 동작합니다. 
스크리너 API가 SSE(Server-Sent Events) 스트림으로 동작하므로 스크립트는 스트림을 구독하여 `{"type": "complete"}` 이벤트가 도착할 때까지의 소요 시간을 측정합니다.

```bash
# 기본 실행 (운영 서버 타겟: https://168.107.55.31.nip.io)
uv run python scripts/benchmark_screener.py

# 로컬 개발 환경 타겟 실행
uv run python scripts/benchmark_screener.py --host http://localhost:8000
```

## 4. 벤치마크 결과 및 로그 분석

실행이 완료되면 루트 디렉토리에 `screener_benchmark_YYYYMMDD_HHMMSS.csv` 형태로 결과가 저장됩니다. CSV 파일에는 시나리오명, 소요 시간(초), 검색된 종목 수(Tickers Found), 성공/실패 여부가 기록됩니다.

### 주요 결과 해석
- **0.1초 미만의 비정상적인 종료**: 과거 발생했던 "Short-circuit" 버그와 같이 잘못된 쿼리로 인해 결과가 즉시 빈 값으로 반환된 경우입니다. (ADR-021 적용으로 현재는 해결 및 400 에러 처리됨)
- **정상적인 연산 소요 시간**: SQLite의 풀스캔 및 윈도우 함수 처리로 인해 시나리오의 무거움에 따라 수 초에서 ~30초 가량이 정상적인 소요 시간입니다.
- **최적화 지표 (In-Memory 도입 완료)**: 물리 디스크 I/O 병목을 제거하기 위해 `file::memory:?cache=shared` 기반의 100% In-Memory DB 아키텍처가 전면 적용되었습니다 (참고: ADR-022). 본 벤치마크를 통해 디스크 기반 연산 대비 소요 시간(Duration)이 수백 밀리초 수준으로 얼마나 획기적으로 줄어들었는지 직접 확인할 수 있습니다.
