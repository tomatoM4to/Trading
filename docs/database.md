# 데이터베이스 설계 및 스키마 명세서 (Database Architecture)

본 문서는 Trading Server의 핵심이 되는 SQLite 데이터베이스(`trading.db`)의 스키마 구조와 Zero-Latency 아키텍처 구현을 위한 상세 설계 철학을 명시합니다.

## 0. 핵심 설계 철학
- **SQLite 기반 Zero-Latency 아키텍처 (In-Memory)**: 모든 트레이딩 전략(돌파 매매 등)과 핫리스트 추출은 KIS API에 실시간으로 의존하지 않고, 오직 로컬 SQLite DB만을 조회하여 연산 지연을 0에 가깝게 만듭니다. 이를 위해 부팅 시 물리적 디스크 DB를 **Shared In-Memory DB**로 100% 로드하며, 커넥션 단절 시 메모리 DB가 삭제(GC)되는 것을 막기 위해 `_keepalive_conn`을 띄워둡니다. 모든 임시 연산(`temp_store`)도 메모리에서 수행합니다 (참고: ADR-022).
- **디스크 I/O 최적화 (WAL & 압축)**: 디스크 스토리지 용량을 절약하고 In-Memory 로딩 시간을 단축하기 위해 모든 테이블은 `WITHOUT ROWID, STRICT` 구조를 띕니다. 불필요한 자동 인덱스를 제거하고, `date`와 `time`을 `INTEGER`로 강제 형변환하여 램(RAM)과 디스크 사용량을 극한으로 압축했습니다.
- **자가 치유 (Self-Healing)**: DB 파일이 없거나 손상되었을 경우, 서버 부팅 시점에 즉시 테이블과 인덱스를 재생성하고 데이터 복구를 시작할 수 있는 구조를 지향합니다.

---

## 1. `stock_codes` (기준 마스터 테이블)
2,400여 개의 순수 매매용 우량주 명단입니다. 

### 테이블 스키마 (WITHOUT ROWID, STRICT)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PRIMARY KEY | 단축코드 (예: 005930) |
| `name` | TEXT | NOT NULL | 한글 종목명 |
| `market` | TEXT | NOT NULL | KOSPI 또는 KOSDAQ |
| `market_cap` | REAL | | 전일기준 시가총액 (억 단위) |
| `total_shares` | REAL | | 상장주수 (천 단위) |
| `margin_rate` | REAL | | 증거금 비율 |
| `credit_able` | TEXT | | 신용주문 가능 여부 |
| `revenue` | REAL | | 매출액 |
| `operating_profit`| REAL | | 영업이익 |
| `net_income` | REAL | | 당기순이익 |
| `roe` | REAL | | ROE (자기자본이익률) |
| `is_halted` | INTEGER | | 거래정지 여부 (1: 정지, 0: 정상) |
| `is_admin_issue` | INTEGER | | 관리종목 여부 (1: 관리, 0: 정상) |
| `is_overheated` | INTEGER | | 단기과열 여부 (1: 과열, 0: 정상) |
| `is_warning` | INTEGER | | 시장경고/투자경고 여부 (1: 경고, 0: 정상) |

---

## 2. `daily_ohlcv` (일봉 테이블)
전 종목의 과거 시계열 데이터(최소 400일 이상)를 저장합니다.

### 테이블 스키마 (WITHOUT ROWID, STRICT)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | INTEGER | PK (Composite) | 거래일자 (YYYYMMDD 형식 정수) |
| `open` | INTEGER | | 시가 |
| `high` | INTEGER | | 고가 |
| `low` | INTEGER | | 저가 |
| `close` | INTEGER | | 종가 |
| `volume` | INTEGER | | 누적 거래량 |
| `amount` | INTEGER | | 누적 거래대금 |

---

## 3. `minute_ohlcv` (분봉 테이블)
장중 실시간 및 과거 분봉(1분봉 등) 데이터를 저장합니다.

### 테이블 스키마 (WITHOUT ROWID, STRICT)
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | INTEGER | PK (Composite) | 거래일자 (YYYYMMDD 형식 정수) |
| `time` | INTEGER | PK (Composite) | 거래시간 (HHMMSS 형식 정수, 9시=90000) |
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
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | TEXT | PK (Composite) | 거래일자 (YYYYMMDD 형식) |
| `foreign_vol` | INTEGER | | 외인 순매수 수량 |
| `foreign_amt` | INTEGER | | 외인 순매수 대금 |
| `inst_vol` | INTEGER | | 기관 순매수 수량 |
| `inst_amt` | INTEGER | | 기관 순매수 대금 |

