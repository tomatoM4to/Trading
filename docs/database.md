# 데이터베이스 설계 및 스키마 명세서 (Database Architecture)

본 문서는 Trading Server의 핵심이 되는 SQLite 데이터베이스(`trading.db`)의 스키마 구조, 데이터 정합성 유지 규칙 및 Zero-Latency 아키텍처 구현을 위한 상세 설계 철학을 명시합니다.

## 0. 핵심 설계 철학
- **Zero-Latency 아키텍처**: 모든 트레이딩 전략(돌파 매매 등)과 핫리스트 추출은 KIS API에 실시간으로 의존하지 않고, 오직 로컬 SQLite DB만을 조회하여 연산 지연을 0에 가깝게 만듭니다.
- **WAL 모드 (Write-Ahead Logging)**: 1개의 SQLite 파일을 다중 워커가 동시에 읽고 쓸 수 있도록 WAL 저널 모드를 활성화하여 동시성 성능을 극대화합니다.
- **자가 치유 (Self-Healing)**: DB 파일이 없거나 손상되었을 경우, 서버 부팅 시점에 즉시 테이블과 인덱스를 재생성하고 데이터 복구를 시작할 수 있는 구조를 지향합니다.

---

## 1. `stock_codes` (기준 마스터 테이블)
매일 오전 08:30 스케줄러에 의해 파싱되어 재생성되는 2,400여 개의 순수 매매용 우량주 명단입니다. 

### 필터링 정책 (저장 전 배제 조건)
- 파생상품(ETF/ETN), 리츠, SPAC, 우선주 배제
- 관리종목, 거래정지, 정리매매 종목 배제
- **단기과열종목, 저유동성종목, (코스닥)투자주의환기종목** 완벽 배제
- DB 및 메모리 최적화를 위해 실시간 트레이딩과 직결되지 않는 `prev_vol`(전일거래량), `capital`(자본금) 컬럼은 제외합니다.

### 테이블 스키마
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PRIMARY KEY | 단축코드 (예: 005930) |
| `name` | TEXT | NOT NULL | 한글 종목명 |
| `market` | TEXT | NOT NULL | KOSPI 또는 KOSDAQ |
| `market_cap` | REAL | | 전일기준 시가총액 (억 단위) |
| `total_shares` | REAL | | 상장주수 (천 단위) |
| `margin_rate` | REAL | | 증거금 비율 |
| `credit_able` | TEXT | | 신용주문 가능 여부 |

---

## 2. `daily_ohlcv` (일봉 테이블)
전 종목의 과거 시계열 데이터(최소 400일 이상)를 저장하며, 매일 장 마감 후 갱신됩니다.

### 데이터 적재 및 정합성 룰
- **수정주가(Adjusted Price)**: KIS API 요청 시 `FID_ORG_ADJ_PRC` 플래그를 활성화하여 액면분할/유상증자 등이 반영된 수정주가를 덮어씁니다 (UPSERT/REPLACE 메커니즘 필수).
- **거래대금(`amount`)**: 일봉 차트에서 세력의 개입 여부를 판단하기 위해 거래량(`volume`) 외에 거래대금 데이터가 필수적입니다.

### 테이블 스키마
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | TEXT | PK (Composite) | 거래일자 (YYYYMMDD 형식) |
| `open` | INTEGER | | 시가 |
| `high` | INTEGER | | 고가 |
| `low` | INTEGER | | 저가 |
| `close` | INTEGER | | 종가 |
| `volume` | INTEGER | | 누적 거래량 |
| `amount` | INTEGER | | 누적 거래대금 |

---

## 3. `minute_ohlcv` (분봉 테이블)
장중 실시간 및 과거 분봉(1분봉 등) 데이터를 저장합니다. KIS API의 1회 반환 캔들 한계(120개)를 돌파하기 위한 고도의 롤링 역추적(Backwards Walking) 로직이 적용됩니다.

### 데이터 정합성 룰 (Boundary Bug 방어)
- **Overlap 처리**: 연속된 API 호출 시 겹치는 캔들이 발생하므로, 반드시 `REPLACE INTO` 또는 UPSERT로 동일 시간대의 중복 삽입을 방어합니다.
- **날짜 횡단(Date Crossing)**: 영업일 경계인 `09:00:00` 캔들에 도달 시, 다음 조회를 위해 날짜 파라미터를 하루(영업일 기준) 빼서 무중단으로 역추적해야 합니다.
- **거래대금 역산 (누적 차분 룰)**:
  - KIS API는 특정 시간 캔들만의 거래대금이 아닌 **'당일 누적 거래대금'**을 반환합니다.
  - 따라서 해당 캔들의 실제 거래대금(`amount`)을 구하려면 `현재 캔들 누적대금 - 이전 캔들 누적대금`의 차분(Diff)을 계산해야 합니다.
  - ⚠️ **예외 (09:00:00 캔들)**: 장 시작 캔들인 `09:00:00`은 차분 계산을 하지 않고, API가 반환한 누적 거래대금 원본 값 자체를 그대로 `amount`로 저장해야 정합성이 100% 보장됩니다.

### 테이블 스키마
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | TEXT | PK (Composite) | 거래일자 (YYYYMMDD) |
| `time` | TEXT | PK (Composite) | 거래시간 (HHMMSS) |
| `open` | INTEGER | | 시가 |
| `high` | INTEGER | | 고가 |
| `low` | INTEGER | | 저가 |
| `close` | INTEGER | | 종가 |
| `volume` | INTEGER | | 단위 거래량 (누적 아님) |
| `amount` | INTEGER | | 단위 거래대금 (누적 아님, 차분 계산됨) |

---

## 4. `daily_investors` (수급 전용 테이블 - 개발 예정)
기관 및 외국인의 자금 유입을 추적하여 Breakout 매매의 신뢰도를 높이기 위한 핫리스트(Hotlist) 추출용 테이블입니다. 

### 테이블 스키마 (초안)
- `ticker`, `date` (PK)
- `foreign_vol` (외인 순매수 수량)
- `foreign_amt` (외인 순매수 대금)
- `inst_vol` (기관 순매수 수량)
- `inst_amt` (기관 순매수 대금)
