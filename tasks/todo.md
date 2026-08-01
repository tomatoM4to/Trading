## Task 1: `ma_alignment` 필터 구현

**Description:** N개의 이평선을 파라미터로 받아 정배열(크기순 정렬) 상태가 지정된 캔들(`duration`) 동안 유지되었는지 판별하는 `_handle_ma_alignment` 함수를 `screener_service.py`에 구현합니다. GC 방어를 위한 동적 유효성 검사를 포함합니다.

**Acceptance criteria:**
- [ ] `lines` 배열(예: `[5, 20, 60]`), `duration`, `timeframe`(daily/minute) 파라미터를 받는다.
- [ ] `duration <= MAX_CANDLES - max_line_window` 유효성 검사를 수행하고 위반 시 ValueError 발생.
- [ ] `(MA_A > MA_B) AND (MA_B > MA_C)` 조건이 `duration` 캔들 내내 True였는지 검증하는 쿼리 생성 및 실행.

**Dependencies:** None

**Files likely touched:**
- `app/schemas/screener.py` (스키마 명세 주석 업데이트)
- `app/services/screener_service.py`

**Estimated scope:** Medium: 2 files

---

## Task 2: `ma_cross` 필터 구현

**Description:** 단기 이평선과 장기 이평선을 파라미터로 받아 지정된 기간(`within`) 내에 특정 방향(`golden` 또는 `dead`)으로 교차가 발생했는지 판별하는 `_handle_ma_cross` 함수를 구현합니다.

**Acceptance criteria:**
- [ ] `short_line`, `long_line`, `within`, `direction`, `timeframe` 파라미터를 받는다.
- [ ] `within <= MAX_CANDLES - max(short, long)` 유효성 검사를 수행한다.
- [ ] `LAG` 함수를 이용해 이전 캔들과 현재 캔들의 대소관계가 역전된 시점(Cross)을 찾는 쿼리 생성 및 실행.

**Dependencies:** None

**Files likely touched:**
- `app/services/screener_service.py`

**Estimated scope:** Medium: 1 file

---

## Task 3: 레거시 `ma_uptrend` 필터 제거

**Description:** 기존의 무겁고 복잡했던 다중 이평선 우상향 필터 로직(`_handle_ma_uptrend`)을 삭제하고, 엔진의 `filter_handlers` 딕셔너리를 새 필터들로 교체합니다.

**Acceptance criteria:**
- [ ] `_handle_ma_uptrend` 함수 삭제
- [ ] `self.filter_handlers` 딕셔너리에 `"ma_alignment"`, `"ma_cross"` 맵핑 등록

**Dependencies:** Task 1, 2

**Files likely touched:**
- `app/services/screener_service.py`

**Estimated scope:** Small: 1 file
