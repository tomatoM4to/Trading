# 스크리너 엔진 (Dynamic Screener Engine)

## 1. 개요 (Overview)
스크리너 엔진은 클라이언트(프론트엔드)에서 전달한 동적 조건(필터 목록과 논리 연산자)을 실시간으로 평가하여, 2,400여 개 전 종목 중 조건에 부합하는 종목 리스트를 추출해내는 핵심 파이프라인 모듈입니다.

1GB RAM 환경이라는 하드웨어적 제약을 극복하기 위해 **"Set-Theory(집합론) 기반 메모리 최적화"**와 **"SQLite Push-down(DB단 연산 위임)"** 패턴을 채택하였습니다. (관련 결정 사항: `ADR-014`)

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
      "type": "ma_alignment",
      "params": {
        "lines": ["ma_daily_20", "ma_daily_60"],
        "duration": 3
      }
    },
    {
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
모든 필터 파이프라인 연산이 끝나면 스칼라 서브쿼리로 추출된 종목 리치 데이터(Enrichment)가 포함된 최종 결과를 반환합니다.
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
      "change_rate": 2.5
    },
    {
      "ticker": "000660",
      "name": "SK하이닉스",
      "market": "KOSPI",
      "market_cap": 1200000000000,
      "close": 165000,
      "amount": 8000000000,
      "change_rate": -1.2
    }
  ]
}
```

### 2.3 Filter Parameter Specification (필터별 파라미터 명세)

현재 시스템에서 지원하는 원자적(Atomic) 필터들의 파라미터 스펙입니다. 클라이언트 UI에서는 이 스펙에 맞춰 `timeframe`(일봉/분봉) 값에 따라 이평선 이름(`ma_daily_5` 또는 `ma5` 등)을 동적으로 조합하여 백엔드로 전송해야 합니다.

#### 1. 이평선 정배열 상태 (`ma_alignment`)
N개의 이평선을 파라미터로 받아, **지정된 순서대로 크기 비교(A > B > C)** 조건이 일정 기간 내내 유지되었는지 검증합니다.
- `lines` (`list[str]`): 정렬 상태를 확인할 이평선 이름 배열 (예: `["ma_daily_5", "ma_daily_20", "ma_daily_60"]`). 입력된 배열의 순서대로 부등호 연산을 엮어 `AND` 조건으로 검사합니다.
- `duration` (`int`): 정배열 상태가 최근 몇 캔들 동안 끊임없이 유지되었는지 검사 (1 이상).
  - *주의사항*: 시스템의 GC 정책(보관 주기)에 따라 `(최대 보관 캔들 수) - (요청한 가장 긴 이평선 일수) - 1` 보다 큰 `duration`을 요청하면 쿼리 에러가 발생합니다.

#### 2. 이평선 교차 이벤트 (`ma_cross`)
특정 기간(within) 내에 단기 이평선이 장기 이평선을 상향(골든) 또는 하향(데드) 돌파했는지 검증합니다.
- `short_line` (`str`): 단기 이평선 이름 (예: `"ma_daily_5"`)
- `long_line` (`str`): 장기 이평선 이름 (예: `"ma_daily_20"`)
- `direction` (`str`): 교차 방향 지정.
  - `"golden"`: 단기선이 장기선을 상향 돌파 (이전 캔들: 단기 <= 장기, 현재 캔들: 단기 > 장기)
  - `"dead"`: 단기선이 장기선을 하향 돌파 (이전 캔들: 단기 >= 장기, 현재 캔들: 단기 < 장기)
- `within` (`int`): 최근 N캔들 이내에 해당 교차 이벤트가 적어도 한 번이라도 발생했는지 검사 (1 이상).
  - 예: `within=1`은 가장 최근 캔들에서 교차가 발생했음을 의미합니다.

#### 3. 이평선 수렴 횡보 (`ma_convergence_consolidation`)
지정된 여러 이평선들의 간격(이격도)이 오차율(%) 이내로 밀집된 상태가 특정 기간 동안 '계속 유지'되었는지 검증합니다.
- `lines` (`list[str]`): 수렴 상태를 확인할 이평선 이름 배열 (예: `["ma_daily_5", "ma_daily_20", "ma_daily_60"]`).
- `threshold` (`float`): 수렴 허용 오차율(%) (예: `2.0`). (최고 이평선 - 최저 이평선) / 최저 이평선 <= (threshold / 100.0) 공식을 사용합니다.
- `duration` (`int`): 이 밀집 상태가 최근 몇 캔들 동안 끊임없이 유지되었는지 검사 (1 이상).

#### 4. 이평선 수렴 지점 (`ma_convergence_point`)
특정 기간 내에 다수의 이평선들이 오차율(%) 이내로 밀집된 시점(이벤트)이 단 한 번이라도 발생했는지 검증합니다.
- `lines` (`list[str]`): 수렴 상태를 확인할 이평선 이름 배열.
- `threshold` (`float`): 수렴 허용 오차율(%) (예: `2.0`).
- `within` (`int`): 최근 N캔들 이내에 해당 수렴 이벤트가 적어도 한 번이라도 발생했는지 검사 (1 이상).

#### 5. 외국인 순매수 상위 랭킹 (`foreign_net_buy_rank`)
당일 장중(가집계) 외국인 순매수(수량 기준) 상위 랭킹 종목을 추출합니다. KIS OpenAPI 랭킹 통신을 1~2회 Bulk 수행합니다.
- `limit` (`int`, optional): 반환받을 상위 랭킹 개수 지정. (기본값 30, 최대 60). 30 초과 시 자동 연속조회(Pagination)가 발생하여 KIS API를 2회 호출합니다.

#### 6. 기관 순매수 상위 랭킹 (`inst_net_buy_rank`)
당일 장중(가집계) 기관계 순매수(수량 기준) 상위 랭킹 종목을 추출합니다. KIS OpenAPI 랭킹 통신을 1~2회 Bulk 수행합니다.
- `limit` (`int`, optional): 반환받을 상위 랭킹 개수 지정. (기본값 30, 최대 60). 30 초과 시 자동 연속조회(Pagination)가 발생하여 KIS API를 2회 호출합니다.

---

## 3. 내부 아키텍처 (Architecture)

### 3.1 Set-Theory (집합론) 파이프라인
파이썬 서버는 2,400개 종목의 OHLCV 데이터를 메모리에 절대 올려두지 않습니다. 각 필터 핸들러는 오직 `Set[str]` (예: `{"005930", "000660"}`) 형태의 종목 코드 껍데기만 반환합니다. 
스크리너 오케스트레이터(`screener_service.py`)는 이 얇은 Set들을 받아 파이썬 내장 `&` (교집합) 또는 `|` (합집합) 연산만을 수행하므로 메모리 사용량이 사실상 제로에 가깝습니다.

### 3.2 SQLite Push-down (DB단 연산)
기술적 지표 계산 로직(이평선 등)은 모두 SQLite 내부로 `Push-down` 시켜 처리합니다.
- **예시 (이평선 정배열 판별)**: `ma_alignment` 모듈은 SQLite 윈도우 함수(`COUNT`, `AVG`)를 사용하여 DB 내부에서 20일선 > 60일선 조건이 최근 3일간 유지되었는지를 쿼리로 계산하고 통과된 Ticker만 꺼내옵니다. 이때 신규 상장주 등 데이터 부족으로 인한 거짓 신호(False Positive)를 막기 위해 `CASE WHEN COUNT() = N`으로 데이터 무결성을 강제 검증합니다.
- **가비지 컬렉터(GC) 방어선**: SQLite 성능 저하 방지와 데이터 보존 주기(일봉 300일, 분봉 7일) 충돌을 막기 위해, 사용자가 입력한 파라미터를 기반으로 최대 탐색 기간(`duration`, `within`)을 동적으로 제한합니다. 초과 시 예외를 발생시켜 DB 락(Lock)을 방지합니다.
- **파라미터 엄격 검증 (Anti-Short-Circuit)**: 잘못된 파라미터(예: `direction="up"`)가 주입되어 SQLite 옵티마이저가 `1=0` 조건으로 쿼리 전체를 건너뛰는(Short-circuit) 것을 막기 위해, 모든 파라미터는 SQL 문자열 조립 전에 엄격히 검증되며 실패 시 즉시 예외(ValueError)를 반환합니다. (참고: `ADR-021`)
- **사전 필터링 최적화 (Pre-filter)**: 윈도우 함수의 연산 파티션 수를 줄여 성능을 극대화하기 위해, 쿼리 최상단에 항상 `active_tickers` CTE를 두어 거래정지(`is_halted=1`) 및 관리종목(`is_admin_issue=1`)을 선행 제외한 후 메인 테이블과 조인합니다. (참고: `ADR-020`)
- **일봉/분봉 동시 지원**: 요청 파라미터(`lines`)에 `ma_daily_20`이 들어오면 `daily_ohlcv`를, `ma20`이 들어오면 `minute_ohlcv`를 동적으로 스캔하여 매매 전략(단기/장기)에 모두 대응합니다.

### 3.3 지연 평가와 API Bulk 호출 (예정 사항)
외국인/기관 순매수 등의 수급 필터는 KIS API를 직접 타야 하므로 매우 무거운 작업입니다.
- **지연 평가(Late Evaluation)**: 이러한 수급 API 필터는 항상 파이프라인의 **가장 마지막**에 실행되도록 강제하여, 앞선 이평선/이격도 필터에서 교집합(AND)으로 수십 개 이하로 추려진 종목에 대해서만 호출을 진행합니다.
- **Bulk 집계 우회**: 또는, KIS의 랭킹 API(국내기관_외국인 매매종목가집계)를 활용하여 단 1번의 호출로 상위 100개 종목 집합(Set)을 통째로 가져와 파이프라인에 얹는 방식으로 Rate Limit(초당 20건) 이슈를 완벽히 우회합니다.
