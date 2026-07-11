# 데이터베이스 설계 및 스키마 명세서 (Database Architecture)

본 문서는 Trading Server의 핵심이 되는 SQLite 데이터베이스(`trading.db`)의 스키마 구조와 Zero-Latency 아키텍처 구현을 위한 상세 설계 철학을 명시합니다.

## 0. 핵심 설계 철학
- **SQLite 기반 Zero-Latency 아키텍처**: 모든 트레이딩 전략(돌파 매매 등)과 핫리스트 추출은 KIS API에 실시간으로 의존하지 않고, 오직 로컬 SQLite DB만을 조회하여 연산 지연을 0에 가깝게 만듭니다.
- **WAL 모드 (Write-Ahead Logging)**: 1개의 SQLite 파일을 다중 워커가 동시에 읽고 쓸 수 있도록 WAL 저널 모드를 활성화하여 동시성 성능을 극대화합니다.
- **자가 치유 (Self-Healing)**: DB 파일이 없거나 손상되었을 경우, 서버 부팅 시점에 즉시 테이블과 인덱스를 재생성하고 데이터 복구를 시작할 수 있는 구조를 지향합니다.

---

## 1. `stock_codes` (기준 마스터 테이블)
2,400여 개의 순수 매매용 우량주 명단입니다. 

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
전 종목의 과거 시계열 데이터(최소 400일 이상)를 저장합니다.

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
장중 실시간 및 과거 분봉(1분봉 등) 데이터를 저장합니다.

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
| 컬럼명 | 타입 | 제약 조건 | 설명 |
|---|---|---|---|
| `ticker` | TEXT | PK (Composite) | 단축코드 |
| `date` | TEXT | PK (Composite) | 거래일자 (YYYYMMDD 형식) |
| `foreign_vol` | INTEGER | | 외인 순매수 수량 |
| `foreign_amt` | INTEGER | | 외인 순매수 대금 |
| `inst_vol` | INTEGER | | 기관 순매수 수량 |
| `inst_amt` | INTEGER | | 기관 순매수 대금 |

