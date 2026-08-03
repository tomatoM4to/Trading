# Implementation Plan: Screener Engine - MA Convergence Filters (Backend)

## Overview
스크리너 엔진에 사용자가 지정한 여러 이동평균선(MA)들이 좁은 간격으로 밀집해 있는 상태를 감지하는 "수렴(Convergence)" 필터 2종을 추가합니다. 
1. `ma_convergence_consolidation`: 지정된 오차율 이내의 수렴 상태가 N 캔들 동안 "계속 유지"되었는지 확인 (수렴 횡보)
2. `ma_convergence_point`: 최근 N 캔들 이내에 단 한 번이라도 수렴 조건을 "터치(만족)"했는지 확인 (수렴 지점)

## Architecture Decisions
- **메모리 최적화 (SQLite Push-down)**: Python의 Pandas로 연산하지 않고, 기존 `ma_alignment` 필터처럼 100% SQLite 윈도우 함수와 서브쿼리(CTE) 내부에서 연산(`MAX`와 `MIN` 활용)을 수행합니다.
- **수렴 판단 공식**: `(최고 이평선 값 - 최저 이평선 값) / 최저 이평선 값 <= (Threshold / 100.0)` 방식을 사용합니다.
- **GC(가비지 컬렉터) 안전성 방어**: 데이터 보관 주기(일봉 300일, 분봉 7일)를 초과하는 `duration` 또는 `within` 요청 시 DB Lock 및 부하를 막기 위해 에러 처리(Validation)를 강제합니다.

## Task List

### Phase 1: Foundation (Docs & Handler Mapping)
- [ ] Task 1: 스크리너 엔진 스펙 문서(`docs/screener.md`)에 신규 2종 필터(`ma_convergence_consolidation`, `ma_convergence_point`)의 파라미터 스펙 추가
- [ ] Task 2: `app/services/screener_service.py` 내 `filter_handlers` 딕셔너리에 신규 필터 2종 등록 (기존 `convergence` 더미 삭제)

### Checkpoint: Foundation
- [ ] 서버가 구동될 때 맵핑 에러가 없는지 확인

### Phase 2: Core Features (SQLite Query Push-down)
- [ ] Task 3: `ma_convergence_consolidation` 쿼리 구현 
  - [ ] 파라미터 `lines`, `threshold`, `duration` 추출
  - [ ] `MAX(line1, line2...)`, `MIN(line1, line2...)` 동적 CTE 생성
  - [ ] `(MAX - MIN) / MIN <= threshold` 검사 로직 생성
  - [ ] `HAVING SUM(is_converged) = duration` 으로 연속 유지 확인
- [ ] Task 4: `ma_convergence_point` 쿼리 구현
  - [ ] 파라미터 `lines`, `threshold`, `within` 추출
  - [ ] CTE 연산은 횡보와 동일하게 생성
  - [ ] `WHERE rn <= within AND is_converged = 1` 로 한 번이라도 발생했는지 확인

### Checkpoint: Complete
- [ ] 두 필터에 대한 단건 API 검증이 성공적으로 통과
- [ ] GC 보관 주기를 넘어서는 파라미터 입력 시 의도된 밸리데이션 에러(ValueError)가 발생하는지 테스트

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| SQLite에서 `MAX()`, `MIN()` 함수 다중 인자 지원 여부 | Med | SQLite 내장 `MAX(val1, val2...)` 스칼라 함수를 동적으로 템플릿화하여 적용 |
| `MIN(val) = 0` 일 경우의 ZeroDivision Error | Low | 주가는 0이 될 수 없으나 방어적으로 `NULLIF(MIN_VAL, 0)` 등 방어 로직 추가 |
