# Spec: In-Memory 휘발성 이평선(MA) 아키텍처 도입

## Objective
기존 SQLite 윈도우 함수 기반의 동적 이평선 계산이 야기하는 메모리 부족(OOM) 및 스크리너 60초 타임아웃 병목을 해결하기 위해, 디스크 I/O를 완벽히 제거한 'In-Memory 휘발성 이평선 전용 DB' 아키텍처를 구축합니다. 
- **대상 사용자**: 1GB RAM(Oracle Cloud) 환경에서 제약 없이 초저지연 스크리너를 가동해야 하는 자동 매매 시스템(및 관리자).
- **성공의 정의**: 디스크 I/O 0% 달성, 스크리너 연산 속도 O(1) 수준 단축, 전체 메모리 점유율 350MB 이내 방어.

## Tech Stack
- Python >= 3.12, FastAPI
- 순수 파이썬(Pure Python) Built-in (deque, dict) - **Pandas 사용 금지**
- SQLite3 (`file::memory:?cache=shared` 기반 인메모리 DB)

## Commands
- **실행**: `uv run fastapi dev app/main.py` (DEBUG 모드) / `uv run python app/main.py` (PROD 모드)
- **린트/포맷**: `uv run ruff check . --fix`, `uv run ruff format .`
- **테스트**: (기존 `admin.py` 통합 검증 라우터를 통한 검증)

## Project Structure (수정/추가 대상)
```text
app/
├── core/
│   ├── database.py       → In-Memory MA 전용 커넥션 분리 로직 추가
│   ├── bootstrap.py      → 08:00 콜드스타트 리빌드(OHLCV 로드 -> MA 덤프) 로직 추가
│   └── scheduler.py      → MA 전용 순수 파이썬 계산 및 메모리 캐시(deque) 로직 추가
├── routes/
│   └── screener.py       → Push-down 쿼리 제거 및 단순 In-memory MA 조회 쿼리로 개편
docs/
└── specs/
    └── in-memory-ma-architecture.md (본 문서)
```

## Code Style & Implementation Rule
- **Pure Python 롤링 윈도우 연산**:
```python
# Pandas 없이 deque를 활용한 O(1) 이평선 갱신 예시
from collections import deque

class MACalculator:
    def __init__(self):
        self.closes = deque(maxlen=200)
    
    def update_and_calculate(self, new_close: float) -> dict:
        self.closes.append(new_close)
        length = len(self.closes)
        
        # 단순 sum 최적화 (파이썬 내장 sum은 C로 구현되어 매우 빠름)
        ma5 = sum(list(self.closes)[-5:]) / min(5, length)
        ma20 = sum(list(self.closes)[-20:]) / min(20, length)
        return {"ma5": ma5, "ma20": ma20}
```

## Testing Strategy
1. **단위 검증**: `test_db_var` ContextVar를 이용하여 테스트용 메모리 DB를 띄우고, 순수 파이썬 연산 결과값과 기존 SQLite 윈도우 함수 계산 결과값이 소수점 아래까지 정확히 일치하는지 비교 검증합니다.
2. **부하 검증**: 2,400개 종목에 대한 콜드스타트 벌크 연산 시 메모리 350MB 초과 여부를 로깅합니다.
3. **통합 검증**: `/admin/test/minute_scheduler` 등을 호출하여 디스크 쓰기(OHLCV)와 메모리 쓰기(MA)가 이원화되어 잘 동작하는지 점검합니다.

## Boundaries
- **Always do**: 메모리 DB에 접근할 때는 파일 락 방지를 위해 명시적 `try...finally: conn.close()` 패턴을 준수한다.
- **Ask first**: MA 연산을 위해 스레드 풀(Thread Pool)이나 멀티프로세싱을 도입하려 할 때. (1GB 환경에서 Context Switching 오버헤드가 더 클 수 있음)
- **Never do**: MA 테이블(`daily_ma`, `minute_ma`)의 데이터를 디스크 DB(`trading.db`)에 `INSERT`하거나 `backup()`으로 동기화하는 행위.

## Success Criteria
1. 콜드스타트 시 디스크 DB의 OHLCV를 읽어 인메모리 MA 테이블이 1분 이내에 셋업된다.
2. 장중 1분봉 적재 시 디스크 I/O 없이 순수 파이썬 연산으로 `ma5` ~ `ma200`이 즉각 업데이트된다.
3. 스크리너 API(`screener/run`) 호출 시 `active_tickers` 내부의 무거운 윈도우 함수가 완전히 사라지고 `SELECT * FROM minute_ma` 형태의 단순 쿼리로 수행된다.
4. 어제 장 이전(>390캔들)의 분봉 데이터를 요청하는 스크리너 쿼리는 즉시 400 Bad Request (정책 제한)를 반환한다.

## Open Questions
- 매일 08:00에 In-memory 테이블을 DROP하고 디스크에서 리빌드하는 트리거를 기존 `SystemScheduler` 크론잡(`add_job`)에 등록하면 될까요, 아니면 08:30 기존 마스터 갱신 로직에 통합시킬까요?
