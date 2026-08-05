# Plan: Screener Query Optimizer

## 1. 개요 (Overview)
`app/services/screener_service.py` 내의 `run_pipeline` 및 `run_pipeline_stream` 로직을 개편합니다.
Flat List 형태의 스크리너 요청을 `OR` 기준으로 분기(Split)하여 여러 개의 `AND` 체인으로 만들고, 각 체인 내부의 필터들을 **휴리스틱 비용(Cost)** 순으로 정렬하여 DB 조회 부하를 최소화합니다.

## 2. 주요 컴포넌트 및 구현 순서
1. **Cost Estimator 구현 (`_estimate_cost` 메서드)**
   - API 기반 랭킹 필터(`foreign_net_buy_rank`, `inst_net_buy_rank`): Cost = `0` (가장 우선 실행). API 통신이지만 반환 셋이 30개 정도로 극히 작아 이후 DB 파티션 크기를 99% 줄여줌.
   - DB 기반 필터(`ma_alignment`, `ma_cross` 등): 파라미터 기반 휴리스틱 공식 적용.
     - `timeframe_weight`: 분봉(minute) = 10, 일봉(daily) = 1
     - Cost = `len(lines) * duration(or within) * timeframe_weight`

2. **AST Splitter & Optimizer 구현 (`_optimize_pipeline` 메서드)**
   - `request.filters`와 `request.operations`를 순회하며 `OR` 연산자를 기준으로 리스트를 쪼갬 (예: `[[A, B], [C, D]]`).
   - 각 `AND` 체인 내부의 필터들을 위에서 만든 Cost를 기준으로 오름차순(가벼운 것부터) 정렬.

3. **엔진 실행부 개편 (`run_pipeline` / `run_pipeline_stream`)**
   - 각 `AND` 체인을 순회하며 교집합(`&`)을 수행. 
   - **중요(Short-circuit)**: 특정 `AND` 체인 실행 중 중간 결과 셋이 빈 집합(`set()`)이 되면, 남은 필터를 무시하고 즉시 종료.
   - 모든 `AND` 체인의 결과 셋을 합집합(`|`) 연산으로 결합.
   - `run_pipeline_stream`의 경우, 프론트엔드가 변경된 순서대로 `progress` 이벤트를 받을 수 있도록 `filter_id`와 누적 남은 개수를 스트리밍.

## 3. 병렬 처리 vs 순차 처리
- `OR` 체인 간의 실행은 병렬(asyncio.gather)로 처리할 수도 있으나, 먼저 안전한 순차(Sequential) 처리로 구현하여 1GB RAM 환경에서의 OOM 및 커넥션 풀 고갈 리스크를 방지합니다.

## 4. 리스크 및 완화 (Mitigation)
- **리스크**: 프론트엔드 UI 진행 상태 막대(Progress Bar)가 필터 재정렬로 인해 예상치 못한 순서로 튀는 현상.
- **완화**: SSE 응답에 고유 `filter_id`를 보내고 있으므로 프론트엔드의 `FilterBlock` 컴포넌트 상태 업데이트 로직이 정상 작동할 것으로 기대됨 (하위 호환성 유지).

## 5. 검증 체크포인트 (Verification)
- [ ] 단일 `AND` 체인 테스트 (가장 가벼운 필터가 먼저 실행되는지 확인)
- [ ] `OR` 연산자 분할 테스트 (두 개의 분리된 체인 결합 확인)
- [ ] `run_pipeline_stream`에서 `progress` 이벤트가 재정렬된 순서대로 정상 방출되는지 확인
