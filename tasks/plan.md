# Plan: Screener Multi-Factor Ranking System

## 1. Components & Dependencies
- `screener.py` (Schemas): 업데이트된 응답 스키마 (`filter_values: dict[str, float]`) 반영
- `screener_service.py` (Engine):
  1. 각 개별 필터 로직(`_handle_ma_alignment`, `_handle_ma_cross`, `_handle_ma_convergence_consolidation`, `_handle_ma_convergence_point`, `_fetch_investor_rank`)에서 Set 대신 `Dict[ticker: str, Dict[filter_id: str, float]]`를 반환하도록 쿼리 수정 및 데이터 구조 변경
  2. 필터 결과 병합(Merge) 로직을 기존의 집합 교집합(`&`) 연산에서 딕셔너리 병합(Key Intersection + Dict Merge)으로 변경
  3. `get_ticker_names`에서 누적된 `filter_values`를 딕셔너리 형태로 함께 반환
- 쿼리 최적화: SQLite `SELECT` 시 `is_aligned`, `is_converged` 등의 판단 결과(1/0)뿐 아니라 `difference`, `divergence` 등의 실제 float 계산값을 추가 선택(Select)

## 2. Implementation Order
1. **[Schema]** `app/schemas/screener.py`에서 응답 스키마 `ScreenerResultItem`에 `filter_values` 필드 추가
2. **[Service - Core]** `app/services/screener_service.py`의 `run_pipeline`, `run_pipeline_stream` 로직 내 교집합 변수를 `Set`에서 `Dict` 기반으로 변경 (`chain_set` -> `chain_dict`)
3. **[Service - Filters]** 각 `_handle_*` 메서드에서 Set 반환을 Dict 반환으로 변경 (쿼리에 float 산출 수식 추가)
4. **[Service - Response]** `get_ticker_names`에서 `tickers` (이제 dict)의 `filter_values`를 `results` 딕셔너리에 주입
5. **[Verify]** `benchmark_screener.py` 실행 및 Swagger UI 응답 체크

## 3. Risks & Mitigations
- **메모리 이슈 (1GB RAM)**: 반환 구조를 딕셔너리로 바꿈에 따라 메모리 사용량이 증가할 수 있음.
  - *Mitigation*: 딕셔너리에 중첩되는 불필요한 메타데이터 없이 순수 float 값만 담으며, Pandas로 변환하는 과정을 엄격히 배제함.
- **SQLite 0으로 나누기 에러**: `MIN()` 값이 0일 경우 수렴도 계산 시 분모가 0이 되어 오류 발생.
  - *Mitigation*: 쿼리 내에서 `NULLIF({min_func}, 0)` 형태로 방어 처리 유지.

## 4. Parallel vs Sequential
- 1단계(스키마)와 2단계(Core Merge 로직)는 병렬로 작성 가능하나, 3단계(각 필터 쿼리 수정)는 2단계 완료 후에 진행해야 테스트가 가능함. (순차적 진행 권장)

## 5. Verification Checkpoints
- Checkpoint 1: 스키마 및 코어 병합 로직 수정 후 서버 부팅 확인 (문법 오류 체크)
- Checkpoint 2: 단일 필터 모듈 쿼리 수정 후 Swagger에서 단일 필터 정상 작동 검증
- Checkpoint 3: 다중 필터(`AND`) 복합 요청 시 Float 값 누적 병합(Merge) 확인
