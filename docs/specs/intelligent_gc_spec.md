# Spec: Intelligent GC (지능형 가비지 컬렉터)

## Objective
기존 캘린더 날짜(시간 경과) 기반으로 데이터를 무조건 삭제하던 GC 로직을 개선하여, 주말이나 긴 연휴, 그리고 종목별 개별 거래 정지 시 발생하는 데이터 소실 및 무결성 훼손을 완벽히 방지합니다.
1. **스마트 트리거**: 매일 새벽 4시에 구동되어, 전날(어제)이 휴장일(주말/연휴)이었다면 삭제 작업을 아예 스킵합니다.
2. **개별 종목 보존**: 전날이 영업일이었다면, 파이썬 for-loop가 아닌 임시 테이블(`TEMP TABLE`)과 윈도우 함수(`DENSE_RANK()`, `ROW_NUMBER()`)를 이용한 단일 SQL 트랜잭션으로, **각 종목이 자신의 실제 거래일 기준 최신 N일(분봉 2일, 일봉 500일)의 데이터를 안전하게 보존**하도록 똑똑하게 삭제합니다.

## Tech Stack
- Python 3.12+ / FastAPI
- APScheduler (백그라운드 크론 스케줄링)
- SQLite (In-Memory `file::memory:`, Window Functions, Temporary Tables)

## Commands
- **Lint**: `uv run ruff check . --fix`
- **Format**: `uv run ruff format .`
- **Dev**: `uv run fastapi dev app/main.py` 

## Project Structure
- `app/core/scheduler.py` 
  - `cleanup_ohlcv_job`: GC 구동 조건(스마트 트리거) 검사 및 임시 테이블 기반 일괄 삭제 SQL 쿼리 적용
  - 하단 스케줄러 등록부: GC 크론 타이머를 `23:00`에서 `04:00`으로 변경

## Code Style
파이썬단에서 `for`문을 돌리며 2,400번 통신하지 않고, **SQL 해시 조인(Hash Join) 패턴**을 강제하여 1GB RAM 환경에서도 O(N)의 극강 퍼포먼스를 내도록 합니다.

```python
# 1. 스마트 트리거 (어제 장이 열렸는가?)
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
cursor.execute("SELECT 1 FROM daily_ohlcv WHERE date = ? LIMIT 1", (yesterday,))
if not cursor.fetchone():
    logger.sched(f"어제({yesterday})는 휴장일이므로 GC를 스킵합니다.")
    return

# 2. 임시 테이블을 활용한 종목별 임계치 계산 및 삭제 (분봉 예시)
cursor.execute("CREATE TEMP TABLE IF NOT EXISTS gc_minute_thresholds (ticker TEXT PRIMARY KEY, threshold_date INTEGER) STRICT")
cursor.execute("DELETE FROM gc_minute_thresholds")
cursor.execute("""
    INSERT INTO gc_minute_thresholds (ticker, threshold_date)
    SELECT ticker, MIN(date)
    FROM (
        SELECT ticker, date, DENSE_RANK() OVER (PARTITION BY ticker ORDER BY date DESC) as rnk
        FROM minute_ohlcv
    )
    WHERE rnk <= 2
    GROUP BY ticker
""")
cursor.execute("""
    DELETE FROM minute_ohlcv
    WHERE date < (SELECT threshold_date FROM gc_minute_thresholds WHERE gc_minute_thresholds.ticker = minute_ohlcv.ticker)
""")
```

## Testing Strategy
- `/admin/test` 라우터를 통해 수동으로 GC를 구동하거나 단위 테스트 스크립트를 작성하여 1) 휴장일에 스킵되는지, 2) 장기간 거래정지 종목의 과거 2일치 데이터가 보존되는지 검증합니다.

## Boundaries
- **Always do**: GC 작업은 반드시 트랜잭션(`with conn:`)으로 묶어 원자성을 보장해야 합니다.
- **Ask first**: 삭제 기준 외에 테이블 스키마 자체를 건드려야 할 상황.
- **Never do**: 외부 공공데이터 API 등을 호출하여 달력을 계산하는 짓(네트워크 의존성 추가)은 절대 하지 않습니다. 오직 DB 데이터만으로 판별합니다. 파이썬 `for`문 2,400번 루프도 절대 금지.

## Success Criteria
1. 월요일이나 연휴 직후 새벽 4시에 GC가 구동되어도, "어제가 휴장일"이었음을 감지하고 데이터가 삭제되지 않고 스킵됨.
2. 장기간(예: 8일) 거래 정지되다 전날 거래가 재개된 종목의 경우, 8일 전의 데이터와 전날 데이터 총 2일치가 완벽히 보존됨.
3. 파이썬 루프 기반 방식(수 분 소요) 대비 실행 시간이 압도적으로 빠른 수 초 이내로 완료됨.

## Open Questions
- 없음 (인터뷰를 통해 완벽히 합의됨)
