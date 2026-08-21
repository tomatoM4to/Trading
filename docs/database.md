# 데이터베이스와 메모리 모델

## 저장 계층

시스템은 두 개의 Shared In-Memory SQLite 데이터베이스와 하나의 디스크 파일을 사용한다.

| 저장소 | URI/경로 | 역할 |
|---|---|---|
| 주 메모리 DB | `file::memory:?cache=shared` | 종목 마스터와 OHLCV 서비스 |
| MA 메모리 DB | `file:ma_db?mode=memory&cache=shared` | 사전 계산 이동평균 |
| 디스크 DB | `data/trading.db` 또는 `SQLITE_DB_PATH` | 재시작 복원용 영속 백업 |

각 메모리 DB는 마지막 연결이 닫히면 사라진다. `_keepalive_conn`, `_keepalive_ma_conn`은 프로세스 수명 동안 DB를 유지하므로 제거하면 안 된다.

## 시작과 동기화

`init_sqlite_connection()`은 디스크 DB가 있으면 SQLite backup API로 주 메모리 DB에 복원한 후 `_USE_IN_MEMORY=True`로 전환한다. 이후 `connect_sqlite()`가 만드는 모든 일반 연결은 메모리 DB를 가리킨다.

`sync_memory_to_disk()`는 메모리 DB를 디스크 파일로 backup한다. 기본 경로보다 `test_db_var`, `SQLITE_DB_PATH`가 우선한다. 디스크 연결에는 WAL과 `synchronous=NORMAL`을 적용한다.
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

`MACalculator`는 종목별 `deque(maxlen=200)`를 사용한다. 부트스트랩은 OHLCV를 시간 오름차순으로 순회해 MA를 bulk insert하며, 장중 수집기는 새 종가를 같은 계산기에 밀어 넣는다.

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
