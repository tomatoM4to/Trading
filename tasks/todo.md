- [ ] Task: 비용 계산(Cost Estimator) 함수 구현
  - Acceptance: `screener_service.py` 내에 `_estimate_cost` 메서드가 추가되고, API 기반 필터는 Cost 0을, DB 기반 필터는 파라미터를 기반으로 올바른 O(N) 비용을 반환해야 함.
  - Verify: 더미 필터 파라미터를 통과시켰을 때 기대한 가중치가 계산되는지 단위 로직 점검.
  - Files: `app/services/screener_service.py`

- [ ] Task: AST 분할 및 정렬(Optimizer) 로직 구현
  - Acceptance: `_optimize_pipeline` 메서드가 추가되어, `filters`와 `operations` 리스트를 `OR` 기준으로 분할하고 각 `AND` 체인을 `_estimate_cost` 순으로 오름차순 정렬해야 함.
  - Verify: 테스트 스크립트로 `A AND B OR C AND D` 입력 시 `[ [A, B], [C, D] ]` (비용순 정렬된 상태)가 반환되는지 확인.
  - Files: `app/services/screener_service.py`

- [ ] Task: `run_pipeline` 엔진 실행부 개편
  - Acceptance: `run_pipeline` 메서드가 최적화된 체인을 받아, 체인별로 교집합(`&`)을 수행(중간 결과 `set()` 시 즉시 종료)하고, 최종적으로 합집합(`|`)을 반환해야 함.
  - Verify: 임의의 쿼리를 보냈을 때 필터가 정상 적용된 Set이 리턴되는지 확인 (기존과 결과 무결성 일치).
  - Files: `app/services/screener_service.py`

- [ ] Task: `run_pipeline_stream` 스트리밍(SSE) 엔진 개편
  - Acceptance: 최적화 로직이 동일하게 적용되고, 재정렬된 순서대로 프론트엔드에 `progress` 이벤트가 올바르게 스트리밍되어야 함.
  - Verify: Postman 등 클라이언트로 SSE 요청 시, 재정렬된 순서대로 `filter_id` 응답이 오는지 확인.
  - Files: `app/services/screener_service.py`
