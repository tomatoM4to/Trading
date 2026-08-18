# 스크리너 엔진 (Dynamic Screener Engine)

## 1. 개요 (Overview)
스크리너 엔진은 클라이언트(프론트엔드)에서 전달한 동적 조건(필터 목록과 논리 연산자)을 실시간으로 평가하여, 2,400여 개 전 종목 중 조건에 부합하는 종목 리스트를 추출해내는 핵심 파이프라인 모듈입니다.

1GB RAM 환경이라는 하드웨어적 제약을 극복하기 위해 **"Multi-Factor Dict 파이프라인 기반 메모리 최적화"**와 **"SQLite Push-down(DB단 연산 위임)"** 패턴을 채택하였습니다. 단순 통과 여부만 판단하던 Set 교집합에서 나아가, 딕셔너리 병합(`|`)을 통해 각 필터의 팩터(강도) 값을 Float로 누적 추출합니다. (관련 결정 사항: `ADR-014`, `ADR-028`)

---

## 2. API 명세서 (API Specification)

- **Endpoint**: `POST /api/screener/run`
- **Description**: 주어진 필터 리스트와 연산자(AND/OR)를 순차적으로 평가하여 종목 목록 반환.

### 2.1 Request Schema (요청)
복잡한 무한 깊이의 재귀 트리를 피하고, 프론트엔드가 직관적으로 관리할 수 있는 **1차원 평면 배열(Flat List)**을 사용합니다.
- `filters`: 적용할 개별 조건들의 목록.
- `operations`: 필터 사이에 들어갈 논리 연산자 목록 (개수는 반드시 `필터 수 - 1`).

```json
{
  "filters": [
    {
      "id": "filter-1",
      "type": "ma_alignment",
      "params": {
        "lines": ["ma_daily_20", "ma_daily_60"],
        "duration": 3
      }
    },
    {
      "id": "filter-2",
      "type": "ma_cross",
      "params": {
        "short_line": "ma_daily_5",
        "long_line": "ma_daily_20",
        "within": 1,
        "direction": "golden"
      }
    }
  ],
  "operations": ["AND"]
}
```

### 2.2 Response Schema (SSE Stream)

기존 JSON 반환 방식에서 HTTP Timeout 방지와 Progressive UX를 위한 **Server-Sent Events (SSE)** 스트리밍(`text/event-stream`)으로 변경되었습니다. 클라이언트는 스트림을 읽으며 다음과 같은 형태의 JSON 이벤트를 순차적으로 수신합니다.

**1. Progress Event (진행 상황)**
각 필터 연산이 완료될 때마다 실시간 남은 티커 수를 반환합니다.
```json
data: {"type": "progress", "filter_id": "ast-node-1234", "remaining": 1500}
```

**2. Complete Event (최종 완료)**
모든 필터 파이프라인 연산이 끝나면 스칼라 서브쿼리로 추출된 종목 리치 데이터(Enrichment)와 각 종목이 획득한 지표 점수(`filter_values`)가 포함된 최종 결과를 반환합니다. 프론트엔드는 이 `filter_values` 내의 Float 값들을 바탕으로 사용자 UI에서 각 팩터(수렴도, 교차폭 등)에 대한 **다중 정렬(Multi-Factor Ranking)** 및 **평균 순위 산출(Ranking View)**을 수행합니다 (참고: `docs/specs/screener_ranking_view.md`).
```json
data: {
  "type": "complete",
  "items": [
    {
      "ticker": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "market_cap": 4500000000000,
      "close": 82000,
      "amount": 15000000000,
      "change_rate": 2.5,
      "filter_values": {
        "ast-node-1234": 1.25,
        "ast-node-5678": 0.5
      }
    },
    {
      "ticker": "000660",
      "name": "SK하이닉스",
      "market": "KOSPI",
      "market_cap": 1200000000000,
      "close": 165000,
      "amount": 8000000000,
      "change_rate": -1.2,
      "filter_values": {
        "ast-node-1234": 3.12,
        "ast-node-5678": 0.2
      }
    }
  ]
}
```

### 2.3 Filter Parameter Specification (필터별 파라미터 명세)

현재 시스템에서 지원하는 원자적(Atomic) 필터들의 파라미터 스펙입니다. 클라이언트 UI에서는 이 스펙에 맞춰 `timeframe`(일봉/분봉) 값에 따라 이평선 이름(`ma_daily_5` 또는 `ma5` 등)을 동적으로 조합하여 백엔드로 전송해야 합니다.

#### 1. 이평선 정배열 상태 (`ma_alignment`)
N개의 이평선을 파라미터로 받아, **지정된 순서대로 크기 비교(A > B > C)** 조건이 일정 기간 내내 유지되었는지 검증합니다.
- **추출 지표 값 (Float)**: 대상 이평선들 간의 이격도 편차율(%). 이 값이 **작을수록** 각 이평선 간의 응집도가 높고 폼이 좋은 상태를 의미합니다. (프론트엔드 정렬: **오름차순** 권장)
- `lines` (`list[str]`): 정렬 상태를 확인할 이평선 이름 배열 (예: `["ma_daily_5", "ma_daily_20", "ma_daily_60"]`). 입력된 배열의 순서대로 부등호 연산을 엮어 `AND` 조건으로 검사합니다.
- `duration` (`int`): 정배열 상태가 최근 몇 캔들 동안 끊임없이 유지되었는지 검사 (1 이상).
  - *주의사항*: 시스템의 GC 정책(보관 주기)에 따라 `(최대 보관 캔들 수) - (요청한 가장 긴 이평선 일수) - 1` 보다 큰 `duration`을 요청하면 쿼리 에러가 발생합니다.

#### 2. 이평선 교차 이벤트 (`ma_cross`)
특정 기간(within) 내에 단기 이평선이 장기 이평선을 상향(골든) 또는 하향(데드) 돌파했는지 검증합니다.
- **추출 지표 값 (Float)**: 교차 당시 단기선과 장기선의 이격 차이 폭(%). 이 값이 **클수록** 강한 모멘텀으로 이평선을 강하게 돌파했음을 의미합니다. (프론트엔드 정렬: **내림차순** 권장)
- `short_line` (`str`): 단기 이평선 이름 (예: `"ma_daily_5"`)
- `long_line` (`str`): 장기 이평선 이름 (예: `"ma_daily_20"`)
- `direction` (`str`): 교차 방향 지정.
  - `"golden"`: 단기선이 장기선을 상향 돌파 (이전 캔들: 단기 <= 장기, 현재 캔들: 단기 > 장기)
  - `"dead"`: 단기선이 장기선을 하향 돌파 (이전 캔들: 단기 >= 장기, 현재 캔들: 단기 < 장기)
- `within` (`int`): 최근 N캔들 이내에 해당 교차 이벤트가 적어도 한 번이라도 발생했는지 검사 (1 이상).
  - 예: `within=1`은 가장 최근 캔들에서 교차가 발생했음을 의미합니다.

#### 3. 이평선 수렴 횡보 (`ma_convergence_consolidation`)
지정된 여러 이평선들의 간격(이격도)이 오차율(%) 이내로 밀집된 상태가 특정 기간 동안 '계속 유지'되었는지 검증합니다.
- **추출 지표 값 (Float)**: 해당 기간 동안의 평균 수렴 오차율(%). 이 값이 **작을수록** 이격이 거의 0에 가깝게 완벽히 수렴했음을 의미합니다. (프론트엔드 정렬: **오름차순** 권장)
- `lines` (`list[str]`): 수렴 상태를 확인할 이평선 이름 배열 (예: `["ma_daily_5", "ma_daily_20", "ma_daily_60"]`).
- `threshold` (`float`): 수렴 허용 오차율(%) (예: `2.0`). (최고 이평선 - 최저 이평선) * 100.0 / 최저 이평선 <= threshold 공식을 사용합니다.
- `duration` (`int`): 이 밀집 상태가 최근 몇 캔들 동안 끊임없이 유지되었는지 검사 (1 이상).

#### 4. 이평선 수렴 지점 (`ma_convergence_point`)
특정 기간 내에 다수의 이평선들이 오차율(%) 이내로 밀집된 시점(이벤트)이 단 한 번이라도 발생했는지 검증합니다.
- **추출 지표 값 (Float)**: 해당 기간 내 달성한 최저 수렴 오차율(%). 이 값이 **작을수록** 완벽한 수렴 지점이 형성되었음을 의미합니다. (프론트엔드 정렬: **오름차순** 권장)
- `lines` (`list[str]`): 수렴 상태를 확인할 이평선 이름 배열.
- `threshold` (`float`): 수렴 허용 오차율(%) (예: `2.0`).
- `within` (`int`): 최근 N캔들 이내에 해당 수렴 이벤트가 적어도 한 번이라도 발생했는지 검사 (1 이상).

#### 5. 외국인 순매수 상위 랭킹 (`foreign_net_buy_rank`)
당일 장중(가집계) 외국인 순매수(수량 기준) 상위 랭킹 종목을 추출합니다. KIS OpenAPI 랭킹 통신을 1~2회 Bulk 수행합니다.
- `limit` (`int`, optional): 반환받을 상위 랭킹 개수 지정. (기본값 30, 최대 60). 30 초과 시 자동 연속조회(Pagination)가 발생하여 KIS API를 2회 호출합니다.

#### 6. 기관 순매수 상위 랭킹 (`inst_net_buy_rank`)
당일 장중(가집계) 기관계 순매수(수량 기준) 상위 랭킹 종목을 추출합니다. KIS OpenAPI 랭킹 통신을 1~2회 Bulk 수행합니다.
- `limit` (`int`, optional): 반환받을 상위 랭킹 개수 지정. (기본값 30, 최대 60). 30 초과 시 자동 연속조회(Pagination)가 발생하여 KIS API를 2회 호출합니다.

#### 7. 이격도 (`disparity_value`)
특정 이평선 대비 현재 주가의 이격도가 지정된 임계치(퍼센트) 이하 혹은 이상인지 판별합니다.
- **추출 지표 값 (Float)**: 판별 당시의 실제 이격도 값(%). (프론트엔드 정렬: 과대낙폭 반등은 오름차순, 모멘텀 돌파는 내림차순 권장)
- `line` (`str`): 기준이 될 이평선 이름 (예: `"ma_daily_20"`)
- `threshold` (`float`): 이격도 임계값(%) (예: `95.0`은 5% 눌림, `105.0`은 5% 돌파를 의미)
- `direction` (`str`): 판별 방향 지정.
  - `"below"`: 현재가 이격도가 threshold 이하인지 검사 (`<=`)
  - `"above"`: 현재가 이격도가 threshold 이상인지 검사 (`>=`)

#### 8. 최대 거래량 매물대 돌파 (`volume_peak_breakout`)
지정된 기간 내 가장 많은 거래량이 터진 단일 캔들(Max Volume Candle)을 핵심 저항선(매물대)으로 삼고, 현재가가 이 캔들의 고가(High)를 상향 돌파했는지 판별합니다.
- **추출 지표 값 (Float)**: 매물대 고가 대비 현재가의 초과 돌파율(%). 이 값이 클수록 저항을 강하게 뚫은 상태입니다. (프론트엔드 정렬: 내림차순 권장)
- `lookback` (`str`): 매물대를 탐색할 과거 기간 (고정 프리셋 사용 필수).
  - 일봉 프리셋: `"1M"` (약 30캔들), `"3M"` (약 60캔들)
  - 분봉 프리셋: `"2H"` (약 120캔들), `"4H"` (약 240캔들)

---

## 3. 내부 아키텍처 (Architecture)

### 3.1 Multi-Factor Dict 파이프라인
파이썬 서버는 2,400개 종목의 OHLCV 데이터를 메모리에 통째로 올려두지 않습니다. 각 필터 핸들러는 통과 여부와 해당 조건의 지표 점수를 담은 `Dict[str, Dict[str, float]]` (예: `{"005930": {"filter_123": 0.5}}`)를 반환합니다.
스크리너 오케스트레이터(`screener_service.py`)는 이 얇은 딕셔너리들을 받아 파이썬 내장 `|` (병합) 연산을 통해 동일한 키(Ticker)가 가진 팩터 점수들을 누적(Intersection/Union)시켜 나가므로, DataFrame이 필요 없으며 메모리 오버헤드가 제로에 가깝습니다.

### 3.2 Pre-calculated In-Memory MA Push-down (DB단 사전 연산 스캔)
극단적인 Zero-Latency와 1GB RAM 환경에서의 메모리 보호를 위해, 무거운 SQLite 윈도우 함수(`AVG OVER`)를 전면 폐기하고 **전용 In-Memory MA DB(`daily_ma`, `minute_ma`)를 활용한 사전 계산(Pre-calculated) 푸시다운** 패턴을 사용합니다 (참고: `ADR-026`, `ADR-027`).
- **사전 계산 테이블 스캔**: 백그라운드 워커 및 서버 부팅 시 파이썬 `collections.deque` 기반의 `MACalculator`가 계산하여 적재해 둔 컬럼(`ma5`, `ma10`, `ma20`, `ma60`, `ma120`, `ma200`)을 단순 조건문(`WHERE curr_ma5 > curr_ma20`)과 `ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY date DESC) <= duration`으로 초고속 스캔합니다.
- **파라미터 엄격 검증 및 AST Injection 방어**: SQL 문자열 조립 전 `VALID_MA_PERIODS = {"5", "10", "20", "60", "120", "200"}` 화이트리스트 검증과 정수 바운드(`1 <= duration <= max_candles`)를 거쳐 악의적인 인젝션과 옵티마이저 Short-circuit 오류를 원천 차단합니다 (참고: `ADR-021`, `ADR-033`).
- **동적 Ticker 푸시다운 (Parameterized Push-down)**: 이전 체인(API 랭킹 등)에서 축소된 종목 리스트는 쿼리 내부에 `WHERE ticker IN (?, ?, ...)` 형태의 Parameterized Query로 안전하게 주입하여 DB 스캔 범위를 극적으로 축소합니다 (참고: `ADR-027`).
- **사전 필터링 최적화 (Pre-filter)**: 첫 번째 필터 실행 시 거래정지(`is_halted=1`) 및 관리종목(`is_admin_issue=1`) 종목을 선행 필터링하여 불필요한 연산을 방지합니다 (참고: `ADR-020`).
- **크로스 DB 조인 (Cross-DB Join for Disparity)**: 이격도(`disparity_value`)는 `ATTACH DATABASE` 구문을 통해 메인 DB(`daily_ohlcv`/`minute_ohlcv`)와 MA DB(`daily_ma`/`minute_ma`)를 단일 트랜잭션으로 조인하여 실시간 푸시다운 연산합니다 (참고: `ADR-035`).
- **초경량 매물대 근사치 (Volume Peak Breakout)**: 무거운 Volume Profile 대신 `ORDER BY volume DESC LIMIT 1` 서브쿼리를 이용해 지정 기간 내 최대 거래량 캔들의 고가를 핵심 저항선으로 판별합니다 (참고: `ADR-035`).

### 3.3 쿼리 옵티마이저와 Short-circuit 연산
다양한 필터가 조합될 때 발생하는 병목을 제거하기 위해 **휴리스틱 쿼리 옵티마이저**가 작동합니다 (참고: `ADR-024`, `ADR-027`).
- **Big O Cost 기반 재정렬**: 클라이언트의 Flat AST는 `OR` 연산을 기준으로 먼저 분할되고, 각 `AND` 체인 내부의 필터들은 시간복잡도 비용(`_estimate_cost`) 오름차순으로 자동 정렬됩니다. In-Memory MA 환경에서는 전체 윈도우 크기가 아닌 실제 스캔 행 수(`k = duration`) 및 타임프레임 가중치(일봉 1.0, 분봉 3.0)를 바탕으로 정확한 비용을 산정합니다.
- **API 랭킹 필터 최우선 실행 (Cost = 0)**: 외국인/기관 순매수 수급 필터는 KIS API 통신이 발생하지만, 1회의 Bulk 조회만으로 모수를 30~60개로 즉시 축소시켜 후속 DB 쿼리의 연산 대상을 99% 증발시키므로 최우선순위(Cost 0)로 실행됩니다.
- **Empty Set 즉시 중단 (Short-circuit)**: 가벼운 필터부터 순차 평가하던 중 중간 결과 집합이 빈 집합(`len(chain_dict) == 0`)이 되면, 뒤에 남은 무거운 필터들의 연산을 즉시 중단(`break`)하여 시스템 자원을 보호합니다.

