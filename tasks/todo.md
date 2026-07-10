## Task 1: FastAPI Admin 라우터 무결성 검증 고도화 (`verify_daily_integrity`)

**Description:** 기존 `/admin/daily/verify` 라우터 함수 내 루프를 수정하여, DB에 존재하지 않는 API 날짜를 발견할 경우 단순 카운트 뿐만 아니라 `missing_dates` 리스트에 실제 날짜(YYYYMMDD)를 기록하도록 만듭니다.

**Acceptance criteria:**
- [ ] `app/routes/admin.py` 라인 540 부근에 `missing_dates = []` 초기화 추가.
- [ ] `if not db_row:` 분기에서 `missing_dates.append(date_val)` 로직 추가.
- [ ] JSON 리턴 딕셔너리(`results.append`) 안에 `"missing_dates": missing_dates` 항목 추가.

**Verification:**
- [ ] Linter 통과 (ruff).
- [ ] `/admin/daily/verify` API 호출 시 JSON 결과에 `missing_dates` 필드가 존재하는지 확인.
