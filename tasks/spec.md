# Spec: 종목 마스터 심화 필터링 및 단일 중앙 스케줄러 시스템

## 1. Objective
단기 돌파(Breakout) 매매 자동화 봇의 안정성을 극대화하기 위해, 시스템 구조를 극도로 단순하고 견고하게 유지합니다. 
- **유니버스 정제**: 2,500개의 전수 검사 대상 중 거래정지, 관리종목, 단기과열, 저유동성, 환기종목 등 자동매매에 치명적인 종목을 원천 배제합니다.
- **아키텍처 확립**: Oracle Cloud(1 OCPU, 1GB RAM)의 한계를 고려하여, 복잡한 다중 스케줄러나 핫리스트(Hotlist) 동적 갱신 로직을 배제하고 **단일 스케줄러(SystemScheduler)**와 단일 큐(Queue) 체제를 채택합니다.
- **Trade-off 수용**: 2,500개 종목을 단일 큐로 순회 시 발생하는 **6분의 레이턴시는 시스템의 단순성과 안정성을 위해 적극적으로 수용**하며, 이를 노이즈(휩소) 필터링의 수단으로 활용하는 묵직한 Breakout 전략을 지향합니다.

## 2. Tech Stack
- Python 3.12+ (FastAPI)
- pandas (데이터 정제)
- sqlite3 (로컬 DB 저장)
- apscheduler (중앙 스케줄링)

## 3. Commands
- Linter/Formatter: `uv run ruff check . --fix && uv run ruff format .`
- Dev Server: `uv run fastapi dev app/main.py`

## 4. Project Structure
```text
app/
 ├── tasks/
 │    ├── init_stock_codes.py  # (수정) KIS 마스터 파일 기반 심화 필터링 적용
 ├── core/
 │    ├── database.py          # (수정) 불필요한 스키마 컬럼(prev_vol, capital) 제거
 │    ├── scheduler.py         # (생성) 기존 auth_scheduler를 확장한 중앙 스케줄러 (SystemScheduler)
 ├── main.py                   # (수정) SystemScheduler 등록 및 구형 스케줄러 제거
```

## 5. Code Style
```python
# 필터링은 Pandas boolean indexing을 연속적으로 체이닝하여 명확성을 높임
# 30분 단일가 매매 종목 차단 (단기과열)
kpi = kpi[kpi["단기과열"].str.strip() == "0"]

# 10분 단일가 매매 종목 차단 (저유동성)
kpi = kpi[kpi["저유동성"].str.strip() != "Y"]
```

## 6. Testing Strategy
- 수동 검증: 서버 구동 후 `trading.db`의 `stock_codes` 테이블 로우 개수가 기존(약 2500개)에서 심화 필터링 적용 후 유의미하게 감소했는지 DB 툴로 확인.
- 스케줄러 검증: `SystemScheduler`가 서버 부팅 시 1회 즉시 실행되고, 매일 22:00(인증) 및 08:30(종목 초기화)에 정상 예약되는지 로깅 확인.

## 7. Boundaries
- **Always**: 마스터 파일(`.mst`) 갱신 시 `sqlite3` 트랜잭션을 사용하여 원자적(`replace`)으로 덮어씁니다.
- **Always**: 스케줄러 인스턴스는 오직 `core.scheduler.SystemScheduler` 하나만 존재해야 하며 싱글톤으로 관리됩니다.
- **Ask first**: Pandas DataFrame의 다른 신규 컬럼을 DB 스키마에 추가할 때 사용자에게 의도 확인.
- **Never**: `daily_ohlcv` 등 타 테이블의 과거 데이터를 임의로 삭제하지 않습니다.
- **Never**: 6분의 레이턴시를 줄이기 위해 워커 스레드를 늘리거나 스케줄러를 분할하는 최적화를 시도하지 않습니다. (안정성 최우선)

## 8. Success Criteria
1. `init_stock_codes.py` 내에 코스피/코스닥 각각 `단기과열`, `저유동성`, `환기종목` 필터링 로직이 추가된다.
2. `prev_vol`과 `capital` 컬럼이 `stock_codes` 테이블 저장 시 제외된다.
3. 매일 오전 08:30에 마스터 DB가 덮어쓰기로 자동 갱신되는 `SystemScheduler`가 동작한다.

## 9. Open Questions
- (해결됨) 스케줄러 통합 여부 -> 중앙 집중형(Centralized) 단일 스케줄러로 확정.
- (해결됨) 6분 레이턴시 수용 여부 -> 시스템 단순성을 위해 기꺼이 수용하기로 확정.
