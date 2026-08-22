# 스크리너 벤치마크 및 부하 테스트 (Screener Benchmark)

## 1. 개요
`scripts/benchmark_screener.py` 스크립트는 Trading Server의 핵심인 **스크리너 엔진(Screener Engine)**의 실시간 성능과 부하 처리 능력을 측정하기 위해 작성되었습니다.

본 벤치마크는 약 2,400개 전 종목을 대상으로 스크리너의 실제 HTTP/SSE 응답 시간을 Oracle Cloud Free Tier(1 OCPU, 1GB RAM)에서 추적합니다. OHLCV는 디스크 SQLite 정본에서 조회하고, 반복 사용하는 이동평균은 Shared In-Memory SQLite의 `daily_ma`와 `minute_ma`에서 조회합니다.

## 2. 벤치마크 시나리오 구성
벤치마크는 실제 탐색에 가까운 Light 7개와 전 종목 장기 구간을 반복 조회하는 Heavy 5개로 나뉩니다. 일봉 MA는 최대 300봉, 분봉 MA는 최대 390봉인 현재 보존 범위 안에서만 기간을 설정합니다.

### ☀️ Light Scenarios (현실적인 단일·OR 조건)
1. **Light 1 (Daily Alignment, 5 Sessions)**: 5·20·60일선 정배열이 최근 5거래일 동안 유지됐는지 검사합니다.
2. **Light 2 (Daily Golden Cross, 20 Sessions)**: 최근 20거래일 안의 5일선·20일선 골든 크로스를 찾습니다.
3. **Light 3 (Minute Golden Cross, 60 Minutes)**: 최근 60분 안의 5분선·20분선 골든 크로스를 찾습니다.
4. **Light 4 (Daily Convergence, 10 Sessions)**: 5·20·60일선이 3% 이내로 10거래일 동안 밀집했는지 검사합니다.
5. **Light 5 (Daily MA20 Disparity Above 105)**: 최신 일봉이 20일선보다 5% 이상 높은 종목을 찾습니다.
6. **Light 6 (Daily 1M Volume Peak Breakout)**: 현재가가 최근 1개월 최대 거래량 캔들의 고가를 돌파했는지 검사합니다.
7. **Light 7 (Three-Way Daily Opportunity OR)**: 최근 20일 골든 크로스, 최근 20일 MA 수렴 지점, 3개월 거래량 매물대 돌파 중 하나 이상을 만족하는 종목을 합집합합니다.

### ⛈️ Heavy Scenarios (극한 스트레스 테스트)
1. **Heavy 1 (Daily 300-Candle Alignment Scan)**: 6개 일봉 MA 정배열을 최대 보존 범위인 300봉에서 전 종목 검사합니다.
2. **Heavy 2 (Minute 390-Candle Alignment Scan)**: 6개 분봉 MA 정배열을 최대 보존 범위인 390봉에서 전 종목 검사합니다.
3. **Heavy 3 (Minute 390-Candle Convergence Scan)**: 6개 분봉 MA의 5% 이내 수렴을 390봉에서 전 종목 검사합니다.
4. **Heavy 4 (Three-Way Full-Scan OR)**: 분봉 300봉 정배열, 300봉 수렴, 390봉 크로스를 각각 독립 실행해 3개 결과를 OR로 합칩니다.
5. **Heavy 5 (Two-Way Multi-Timeframe OR)**: 일봉 300봉 수렴과 분봉 390봉 크로스를 각각 전 종목 실행해 두 결과를 OR로 합칩니다.

Heavy에는 투자자 랭킹 필터나 AND 체인을 넣지 않습니다. 랭킹 API 또는 앞선 AND 필터가 후보를 축소하면 뒤의 전 종목 DB 연산이 가벼워져 부하 측정 목적이 훼손되기 때문입니다.

## 3. 실행 방법

벤치마크 스크립트는 `uv` 환경 또는 파이썬 가상환경에서 `requests` 라이브러리를 통해 동작합니다.
스크리너 API가 SSE(Server-Sent Events) 스트림으로 동작하므로 스크립트는 `complete` 이벤트가 도착할 때까지의 소요 시간을 측정합니다. `error` 이벤트를 받거나 `complete` 없이 스트림이 끝나면 해당 시나리오를 실패로 기록합니다.

```bash
# 기본 실행 (현재 운영 서버 타겟: https://168.107.28.167.nip.io)
uv run python scripts/benchmark_screener.py

# 로컬 개발 환경 타겟 실행
uv run python scripts/benchmark_screener.py --host http://localhost:8000
```

## 4. 벤치마크 결과 및 로그 분석

실행이 완료되면 루트 디렉토리에 `screener_benchmark_YYYYMMDD_HHMMSS.csv` 형태로 결과가 저장됩니다. CSV 파일에는 시나리오명, 소요 시간(초), 검색된 종목 수(Tickers Found), 성공/실패 여부가 기록됩니다.

### 주요 결과 해석
- **시나리오 버전 경계**: 2026-08-22 12:00까지의 결과는 기존 5 Light + 5 Heavy 구성입니다. 12:18부터 적용된 새 7 Light + 5 Heavy 결과와 시나리오 번호만으로 직접 비교하지 않습니다.
- **0.1초 미만의 비정상적인 종료**: 잘못된 쿼리로 인해 결과가 즉시 빈 값으로 반환된 과거 short-circuit 사례일 수 있습니다. 현재 입력 계약은 [`screener.md`](screener.md)를 따릅니다.
- **정상적인 연산 소요 시간**: SQLite의 풀스캔 및 윈도우 함수 처리로 인해 시나리오의 무거움에 따라 수 초에서 ~30초 가량이 정상적인 소요 시간입니다.
- **저장 계층 해석**: OHLCV와 종목 마스터는 WAL이 적용된 디스크 `trading.db`가 정본이고, 사전 계산 MA만 Shared In-Memory DB에 유지합니다. 현재 구조는 [`database.md`](database.md)를 참고합니다.

## 5. 벤치마크 결과 히스토리
아래에는 Oracle Cloud 1GB RAM 운영 서버에서 측정한 결과만 보관합니다. 로컬 측정값은 운영 성능과 직접 비교하기 어려워 결과 파일과 히스토리에서 제외합니다.

### ☁️ 운영 서버 (Oracle Cloud, 1GB RAM)
1. 초기 최적화 전 (버그 포함)
- 참고: 1, 2차 테스트는 `Short-circuit` 버그로 인해 쿼리가 무시되어 0초로 기록된 결과입니다.
- [screener_benchmark_20260804_145625.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_145625.csv)
- [screener_benchmark_20260804_150706.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_150706.csv)

2. 버그 해결 후 정밀 테스트
- 참고: 정상적으로 DB 쿼리가 수행되었으나, 디스크 I/O 병목으로 인해 쿼리 소요 시간이 수십 초에 달했습니다.
- [screener_benchmark_20260804_152738.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_152738.csv)

3. In-Memory DB 최적화 도입
- 최적화 성과: Disk I/O를 0으로 만들어 전반적인 속도는 올랐으나, 분봉 데이터 윈도우 함수 처리 시 1GB RAM 환경의 연산 한계로 인해 60초 타임아웃(Timeout)이 다수 발생했습니다.
- [screener_benchmark_20260804_222615.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_222615.csv)
- [screener_benchmark_20260804_224407.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260804_224407.csv)

4. 1차~4차 아키텍처 최적화 전면 적용 (서버 최종본)
- 최적화 성과: 로컬에서 검증된 최적화 기법(AST Cost 정렬, 동적 Ticker 푸시다운, 단방향 윈도우 등)을 1GB RAM 운영 서버에 모두 적용 후 측정한 최종 결과입니다. 풀스캔이 발생하는 단순 시나리오(Light 1~4)는 11~23초 소요되나, 수급 필터나 복합 조건이 포함된 시나리오들(Light 5, Heavy 1~5)은 사전 파티션 축소(지연 평가) 및 Short-circuit 덕분에 **전부 0.6초 이내(기존 60초 타임아웃 대비 99% 이상 단축)**에 처리되는 극적인 성능 최적화를 달성했습니다.
- [screener_benchmark_20260806_185510.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260806_185510.csv)

5. 인메모리 MA 엔진 도입 전 (서버 베이스라인 재측정)
- 참고: 현재 파이썬 MA 엔진 도입 직전에 측정한 과거 서버 성능입니다. 분봉 윈도우 풀스캔 연산(Light 2, Light 4) 시 약 28~30초가 소요됐습니다.
- [screener_benchmark_20260808_213722.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260808_213722.csv)

6. 인메모리 MA 도입 후
- 30%~50% 개선
- [screener_benchmark_20260809_000809.csv](https://github.com/tomatoM4to/Trading/blob/main/docs/benchmark-result/screener_benchmark_20260809_000809.csv)

7. 디스크 OHLCV 정본 + MA 전용 인메모리 구조 적용 후 최신 측정

- 측정 시각: 2026-08-22 12:00 KST
- 대상: `https://168.107.28.167.nip.io`
- 결과: 10개 시나리오 모두 성공
- 단순 전 종목 MA 필터는 일봉 약 5.4초, 분봉 약 9.7~12.3초가 걸렸습니다.
- 투자자 랭킹이 AND 체인에서 먼저 후보를 줄이는 복합 시나리오는 약 0.27~0.61초가 걸렸습니다.
- 결과 종목 수와 응답 시간은 장중 데이터 적재 상태와 KIS 투자자 랭킹 응답에 따라 달라질 수 있습니다.
- [screener_benchmark_20260822_120010.csv](benchmark-result/screener_benchmark_20260822_120010.csv)

8. 현실적 탐색 기간과 독립 Heavy 스캔을 적용한 새 기준선

- 측정 시각: 2026-08-22 12:18 KST
- 대상: `https://168.107.28.167.nip.io`
- 결과: 새 7 Light + 5 Heavy 시나리오 12개 모두 성공
- 신규 이격도 필터는 6.711초, 1개월 거래량 매물대 돌파는 9.774초였습니다.
- 일반 단독 조건은 5.358~9.774초였고, 3개 일봉 조건 OR은 21.520초였습니다.
- Heavy 단독 전 종목 스캔은 8.971~14.531초였습니다.
- 독립 쿼리를 모두 실행하는 Heavy OR는 2분기 29.269초, 3분기 43.074초였습니다.
- Heavy 1·2의 결과 0건은 오류가 아니라 300·390봉 전체에서 정배열을 계속 유지해야 하는 엄격한 조건의 결과입니다.

| 시나리오 | 시간(초) | 종목 수 |
|---|---:|---:|
| Light 1 · 일봉 정배열 5일 | 5.407 | 323 |
| Light 2 · 일봉 골든 크로스 20일 | 6.024 | 2,041 |
| Light 3 · 분봉 골든 크로스 60분 | 9.694 | 2,301 |
| Light 4 · 일봉 수렴 10일 | 5.358 | 69 |
| Light 5 · 일봉 MA20 이격도 105 이상 | 6.711 | 480 |
| Light 6 · 일봉 1개월 거래량 매물대 돌파 | 9.774 | 629 |
| Light 7 · 일봉 3분기 OR | 21.520 | 2,158 |
| Heavy 1 · 일봉 300봉 정배열 | 8.971 | 0 |
| Heavy 2 · 분봉 390봉 정배열 | 12.815 | 0 |
| Heavy 3 · 분봉 390봉 수렴 | 14.531 | 1,607 |
| Heavy 4 · 분봉 전 종목 3분기 OR | 43.074 | 2,285 |
| Heavy 5 · 일봉·분봉 2분기 OR | 29.269 | 2,256 |

- [screener_benchmark_20260822_121829.csv](benchmark-result/screener_benchmark_20260822_121829.csv)
