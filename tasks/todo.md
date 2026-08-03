## Task 1: `ScreenerEngine` 내 KIS API 통신 헬퍼 함수 구현

**Description:** KIS OpenAPI `FHPTJ04400000` (가집계 랭킹) 엔드포인트를 비동기 호출하고, `limit` 파라미터에 따라 필요 시 2페이지까지 연속조회(Pagination)하여 티커 Set을 반환하는 핵심 공통 로직을 작성합니다.

**Acceptance criteria:**
- [ ] `_fetch_investor_rank(etc_cls_code, limit)` 형태의 헬퍼 메서드가 추가됨
- [ ] 1회 호출 시 30개, `limit > 30`일 경우 `tr_cont="N"`과 `ctx_area` 값을 사용해 추가 1회 더 호출함
- [ ] 반환값은 6자리 티커 코드로 구성된 `Set[str]`임 (중복 제거 포함)

**Verification:**
- [ ] 단위/수동 테스트 시 `limit=60`을 주었을 때 API가 2번 정상 호출되고 약 60개의 티커가 반환됨을 로그로 확인

**Dependencies:** None

**Files likely touched:**
- `app/services/screener_service.py`

**Estimated scope:** Small: 1 file

---

## Task 2: 스크리너 엔진에 신규 필터 핸들러 연결

**Description:** 새로 작성된 헬퍼 함수를 이용해 '외국인 순매수 상위'와 '기관 순매수 상위'를 처리하는 핸들러를 추가하고, 파이프라인(`filter_handlers`)에 등록합니다.

**Acceptance criteria:**
- [ ] `_handle_foreign_net_buy_rank` 메서드 구현 (`etc_cls_code="1"`)
- [ ] `_handle_inst_net_buy_rank` 메서드 구현 (`etc_cls_code="2"`)
- [ ] `ScreenerEngine.__init__` 의 `filter_handlers` 딕셔너리에 매핑 추가
- [ ] `params`에서 `limit` 값을 추출하여 헬퍼 함수로 전달 (기본값 30)

**Verification:**
- [ ] 앱을 실행하고 `/api/screener/run` 등으로 해당 필터를 포함한 요청을 보냈을 때 정상적으로 에러 없이 동작함을 확인

**Dependencies:** Task 1

**Files likely touched:**
- `app/services/screener_service.py`
- `app/schemas/screener.py` (필요 시 주석 업데이트)

**Estimated scope:** Small: 2 files

---

## Task 3: 문서 업데이트 (`docs/screener.md`)

**Description:** 추가된 2개의 필터 타입과 사용 가능한 파라미터(`limit`)를 클라이언트 개발자용 명세서에 추가합니다.

**Acceptance criteria:**
- [ ] `foreign_net_buy_rank` 및 `inst_net_buy_rank` 타입에 대한 설명 추가
- [ ] `limit` 파라미터 (기본 30, 최대 60 연속조회 지원) 설명 추가

**Verification:**
- [ ] 마크다운 문서가 가독성 있게 렌더링되는지 수동 점검

**Dependencies:** Task 2

**Files likely touched:**
- `docs/screener.md`

**Estimated scope:** Small: 1 file
