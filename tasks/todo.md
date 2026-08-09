- [ ] Task: 1. ScreenerResultItem 스키마 업데이트
  - Acceptance: `ScreenerResultItem` 모델에 `filter_values: dict[str, float]`가 선택적으로 추가됨.
  - Verify: 서버 기동 시 Pydantic 스키마 에러가 발생하지 않음.
  - Files: `app/schemas/screener.py`

- [ ] Task: 2. 스크리너 코어 파이프라인(Dict Merge) 로직 변경
  - Acceptance: `run_pipeline` 및 `run_pipeline_stream`의 `chain_set`이 `chain_dict`로 변경되며, 두 딕셔너리의 교집합(Key)과 `filter_values` 병합 로직이 구현됨. (API 랭킹 필터들은 기본값 0.0을 반환하도록 수정)
  - Verify: 기존 `set()` 연산 코드가 `dict` 연산으로 정상 치환되었는지 육안 확인.
  - Files: `app/services/screener_service.py`

- [ ] Task: 3. 수렴(Convergence) 필터 쿼리 및 반환값 수정
  - Acceptance: `_handle_ma_convergence_consolidation` 및 `_handle_ma_convergence_point` 쿼리에서 오차율(Float)을 SELECT하여 딕셔너리로 반환함.
  - Verify: 수렴 필터 단독 요청 시 `filter_values`에 오차율 값이 담겨 오는지 확인.
  - Files: `app/services/screener_service.py`

- [ ] Task: 4. 정배열(Alignment) 및 크로스(Cross) 필터 쿼리 및 반환값 수정
  - Acceptance: `_handle_ma_alignment`에서 이격도 편차율(Float)을, `_handle_ma_cross`에서 차이 폭(Float)을 SELECT하여 딕셔너리로 반환함.
  - Verify: 각 필터 단독 요청 시 `filter_values`에 값이 담겨 오는지 확인.
  - Files: `app/services/screener_service.py`

- [ ] Task: 5. get_ticker_names에 결과 매핑 및 벤치마크 테스트
  - Acceptance: `get_ticker_names`가 딕셔너리를 받아 최종 결과 리스트의 `filter_values` 필드에 맵핑해주며, `benchmark_screener.py` 실행 시 무사히 통과됨.
  - Verify: `benchmark_screener.py` 실행 후 `Success` 로그 확인 및 SSE 응답 결과 완벽성 검증.
  - Files: `app/services/screener_service.py`, `scripts/benchmark_screener.py`
