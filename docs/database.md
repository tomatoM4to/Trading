# 데이터베이스와 메모리 모델

## 저장 계층

시스템은 주 데이터용 디스크 SQLite와 이동평균 전용 Shared In-Memory SQLite를 사용한다.

디스크 DB는 서비스가 조회하는 canonical 데이터지만 KIS 원본에서 다시 만들 수 있는 재구축 가능한 로컬 저장소다. DB 삭제는 애플리케이션을 정상 종료한 상태에서만 수행하며, 삭제 후에는 콜드 스타트가 끝날 때까지 데이터와 MA가 단계적으로 준비된다. 배포 전 사본은 필수 영속 백업이 아니라 외부 API 장애나 신규 코드 실패 시 빠르게 되돌리기 위한 안전망이다.

| 저장소 | URI/경로 | 역할 |
|---|---|---|
| 디스크 DB | `data/trading.db` 또는 `SQLITE_DB_PATH` | 종목 마스터와 OHLCV 정본 |
| MA 메모리 DB | `file:ma_db?mode=memory&cache=shared` | 사전 계산 이동평균 |

MA 메모리 DB는 마지막 연결이 닫히면 사라진다. `_keepalive_ma_conn`은 프로세스 수명 동안 MA DB를 유지하므로 제거하면 안 된다. `test_mem_var`로 만든 테스트 DB는 테스트가 별도 keep-alive 연결을 소유한다.

## 시작과 동기화

`init_sqlite_connection()`은 디스크 DB에 직접 연결해 WAL과 주 데이터 스키마를 보장하고, 별도로 MA Shared In-Memory DB와 keep-alive 연결을 생성한다. 이후 `connect_sqlite()`가 만드는 일반 연결은 계속 디스크 정본을 가리킨다.

호환 이름인 `sync_memory_to_disk()`는 운영 경로에서 디스크 정본의 WAL을 체크포인트한다. 관리자 통합 테스트가 `mem_conn`을 명시적으로 전달한 경우에만 테스트 메모리 DB를 `test_db_var` 파일로 backup한다. 디스크 연결에는 WAL과 `synchronous=NORMAL`을 적용한다.
백업 실패는 로그를 남긴 뒤 호출자에게 예외를 다시 전달하므로 스케줄러와 관리자 작업이 성공으로 오인하지 않는다.

## 주 테이블

### `stock_codes`

종목 코드, 이름, 시장, 시가총액·주식수·재무 지표와 거래정지·관리·과열·경고 상태를 보관한다. 기본 키는 `ticker`다.

### `daily_ohlcv`

복합 기본 키 `(ticker, date)`를 사용한다. `date`, 가격, 거래량, 거래대금은 `INTEGER`다.

### `minute_ohlcv`

복합 기본 키 `(ticker, date, time)`을 사용한다. `date`는 `YYYYMMDD`, `time`은 `HHMMSS` 형태의 `INTEGER`다. `amount`는 nullable이다.

모든 주 테이블은 `WITHOUT ROWID, STRICT`다.

## MA 테이블

`daily_ma`와 `minute_ma`는 MA 전용 메모리 DB에만 존재한다.

- 공통 컬럼: `ma5`, `ma10`, `ma20`, `ma60`, `ma120`, `ma200`
- `daily_ma` 기본 키: `(ticker, date)`
- `minute_ma` 기본 키: `(ticker, date, time)`
- 값은 `REAL`, 준비되지 않은 기간은 `NULL`
- `daily_ma`는 스크리너 최대 300봉과 교차 직전 봉을 위해 종목당 최신 301개를 유지한다.
- `minute_ma`는 최대 390봉과 교차 직전 봉을 위해 종목당 최신 391개를 유지한다.

`MACalculator`는 종목별 `deque(maxlen=200)`를 사용한다. 부트스트랩은 보존된 OHLCV를 종목별 시간 오름차순으로 순회해 200일·200분선까지 계산한 다음 결과 테이블만 위 상한으로 정리한다.

장중 분봉 수집은 API 페이지를 받은 순서대로 상태형 계산기에 누적하지 않는다. 최신 391개 결과의 첫 행에도 최대 200분선을 계산할 수 있도록 종목별 수집 완료 후 canonical OHLCV 최신 590개(`391 + 200 - 1`)를 시간순으로 읽고, 로컬 계산기로 재계산한 뒤 해당 종목의 `minute_ma`를 교체한다. 일봉 수집도 중복 범위 upsert 후 해당 종목의 canonical OHLCV에서 다시 계산해 멱등성을 보장한다.

MA 기간에 필요한 캔들이 부족하면 해당 컬럼은 `NULL`이다. 스크리너는 `IS NOT NULL` 조건으로 그 종목만 제외하며 요청 전체를 오류로 처리하지 않는다. 차트는 OHLCV와 함께 계산 불가능한 MA 값을 `null`로 반환한다.

## 연결 수명주기

Python의 `with sqlite3.connect(...)`는 트랜잭션만 관리하고 연결을 닫지 않는다. 모든 독립 연결은 다음 형태를 지킨다.

```python
conn = connect_sqlite()
try:
    ...
finally:
    conn.close()
```

FastAPI 요청에서는 `get_db()`와 `get_ma_db()` dependency가 같은 원칙으로 연결을 닫는다.

## 테스트 DB 라우팅

`test_db_var`는 현재 비동기 컨텍스트에만 DB 파일 경로를 덮어쓴다. 관리자 통합 검증은 이를 사용해 운영 DB 대신 `test_trading.db`로 라우팅하고 작업이 끝나면 ContextVar 토큰을 반드시 reset한다.

`test_mem_var`는 테스트 전용 메모리 URI를 우선 적용한다. 동적 메모리 테스트에서는 별도 keep-alive 연결이 필요하다.

## 쿼리 원칙

- 값은 `?` placeholder로 바인딩한다.
- 동적 컬럼은 정적 화이트리스트에서만 고른다.
- 전 종목 스크리너는 MA 테이블의 사전 계산 값을 사용한다.
- 단일 종목 차트는 제한된 행을 대상으로 윈도 함수를 사용할 수 있다.
- 날짜와 시간은 DB 입력 전에 `int`로 변환한다.
- 임시 테이블은 `PRAGMA temp_store=MEMORY` 설정을 전제로 한다.
