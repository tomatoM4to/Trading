## Task 1: Backend Schema & Service Update

**Description:** `ScreenerResultItem` 스키마를 확장하고, `screener_service.py`의 `get_ticker_names` 함수에서 `stock_codes`, `minute_ohlcv`, `daily_ohlcv`를 조인하여 확장된 데이터를 반환하도록 수정합니다.

**Acceptance criteria:**
- [ ] `app/schemas/screener.py`의 `ScreenerResultItem`에 `market`, `market_cap`, `close`, `amount`, `change_rate` 필드가 추가됨.
- [ ] `app/services/screener_service.py`의 `get_ticker_names` 함수가 3개 테이블에서 필요한 데이터를 가져와 객체에 매핑함.
- [ ] `change_rate` (등락률)가 파이썬 로직 또는 쿼리에서 `(현재가 - 전일종가) / 전일종가 * 100`으로 계산됨.

**Verification:**
- [ ] 백엔드 서버가 에러 없이 구동됨 (uvicorn)
- [ ] 스웨거 테스트 또는 curl 호출 시 반환 JSON에 신규 필드가 포함됨

**Dependencies:** None

**Files likely touched:**
- `app/schemas/screener.py`
- `app/services/screener_service.py`

**Estimated scope:** Small: 1-2 files

---

## Task 2: Frontend Types & Components Update

**Description:** 프론트엔드의 `ScreenerResult` 타입을 백엔드 스키마 변경에 맞게 업데이트하고, `ScreenerResultTable` 컴포넌트에 새로운 컬럼을 추가하며, 거래대금과 시가총액을 억 단위로 포맷팅합니다.

**Acceptance criteria:**
- [ ] `web/components/screener/ScreenerResultTable.tsx`의 `ScreenerResult` 인터페이스에 신규 필드가 추가됨.
- [ ] 테이블 헤더와 셀에 '시장', '현재가', '등락률', '당일 거래대금', '시가총액' 컬럼이 추가됨.
- [ ] 시가총액과 거래대금이 한국어 단위(예: "4500000000000" -> "4.5조", "15000000000" -> "150억")로 포맷팅됨.
- [ ] 등락률이 양수면 빨간색, 음수면 파란색 텍스트로 렌더링됨.

**Verification:**
- [ ] 프론트엔드 서버가 빌드되고 화면 렌더링에 에러가 없음.
- [ ] 브라우저에서 스크리너 탭 진입 후 검색 시 UI가 깨지지 않고 데이터가 올바르게 렌더링됨.

**Dependencies:** Task 1

**Files likely touched:**
- `web/components/screener/ScreenerResultTable.tsx`
- 필요 시 포맷팅 유틸리티 함수 파일 추가/수정

**Estimated scope:** Small: 1-2 files
