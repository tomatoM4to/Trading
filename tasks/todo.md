## Task 1: Update Database Schema Documentation

**Description:** `docs/database.md` 내 `stock_codes` 테이블 명세에 신규로 추가될 재무 지표와 위험 지표 컬럼들을 추가하여 아키텍처 문서를 최신화합니다.

**Acceptance criteria:**
- [ ] `docs/database.md` 내 `stock_codes` 표에 `revenue`, `operating_profit`, `net_income`, `roe` 등의 재무 컬럼이 추가되어야 함.
- [ ] `is_halted`, `is_admin_issue`, `is_overheated` 등의 플래그 컬럼이 추가되어야 함.

**Verification:**
- [ ] Manual check: 마크다운 파일이 올바르게 렌더링되고 컬럼명이 향후 코드와 일치하는지 눈으로 확인.

**Dependencies:** None

**Files likely touched:**
- `docs/database.md`

**Estimated scope:** Small: 1 file

---

## Task 2: Refactor init_stock_codes.py Filtering & Mapping

**Description:** 기존에 '관리종목', '단기과열' 등 위험 종목을 드롭하던 로직을 완화하고, 코스피/코스닥의 신규 지표(재무, 위험 플래그)를 통일된 영문 컬럼명으로 매핑하여 SQLite에 밀어넣도록 코드를 수정합니다.

**Acceptance criteria:**
- [ ] '보통주(ST)' 필터링만 남기고, 상태 불량 종목(거래정지, 관리종목 등) 드롭 로직을 삭제.
- [ ] `kpi_cols`와 `kdq_cols` 딕셔너리에 신규 컬럼 매핑 추가.
- [ ] Y/N 등 텍스트 플래그를 Integer(1/0)로 변환하거나 표준화.
- [ ] 신규 재무 데이터 컬럼들을 `numeric_cols` 리스트에 포함하여 0으로 널(null) 처리.

**Verification:**
- [ ] Build succeeds: 스크립트를 독립적으로 실행(`uv run python app/tasks/init_stock_codes.py`)하여 오류가 없는지 확인.
- [ ] Manual check: SQLite 뷰어(또는 쿼리)로 `stock_codes` 테이블을 조회하여 컬럼 구조와 2,400여 개 데이터가 올바른지 확인.

**Dependencies:** Task 1

**Files likely touched:**
- `app/tasks/init_stock_codes.py`

**Estimated scope:** Small: 1 file
