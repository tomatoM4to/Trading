# Implementation Plan: Atomic MA Screener Filters

## Overview
기존의 무거운 다중 이평선 우상향 필터(`ma_uptrend`)를 제거하고, '상태(ma_alignment)'와 '이벤트(ma_cross)' 단위로 쪼개진 2개의 초경량 원자적 필터를 스크리너 엔진(`screener_service.py`)에 구현합니다. 더불어 GC 주기에 기반한 동적 duration 방어 로직을 추가하여 1GB RAM 환경을 철저히 보호합니다.

## Architecture Decisions
- **Filter 분리**: `ma_alignment`(정배열 상태 유지), `ma_cross`(단/장기 교차) 2개의 독립적인 필터로 구현하여 SQL 쿼리를 극도로 단순화합니다.
- **Set-Theory 파이프라인 연동**: 기존 `screener_service.py`의 `ScreenerEngine.run_pipeline`은 수정하지 않고, 새로운 핸들러(`_handle_ma_alignment`, `_handle_ma_cross`)만 추가하여 기존 파이프라인 구조에 100% 완벽히 호환되게 합니다.
- **Dynamic Duration Limits**: 일봉(200 영업일), 분봉(1950 캔들) GC 제한에 맞춰 요청된 파라미터의 최대 이평선 길이를 역산하여, 최대 허용 `duration` 한계값을 강제합니다. 초과 시 즉각적으로 예외(Error)를 발생시킵니다.

## Task List

### Phase 1: Atomic Filters Implementation
- [ ] Task 1: `ma_alignment` 필터 구현 (상태 필터)
- [ ] Task 2: `ma_cross` 필터 구현 (이벤트 필터)

### Checkpoint: Foundation
- [ ] 더미 필터 파라미터를 활용해 SQLite SQL 문법에 오류가 없는지 `screener_service.py` 내부 동작 검증

### Phase 2: Cleanup and Refactoring
- [ ] Task 3: 레거시 `ma_uptrend` 필터 제거 및 엔진 핸들러 매핑 업데이트

### Checkpoint: Complete
- [ ] 전체 스크리너 파이프라인 오류 없이 정상 작동 확인

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 윈도우 함수 성능 저하 | Med | 복잡도를 낮춘 단순한 논리 연산식과 `ROWS BETWEEN` 조합으로 빠른 인덱스 스캔 유도. |
| 프론트엔드 연동 변경점 | Low | 기존 필터 파라미터 구조가 완전히 바뀌므로 스펙(`docs/screener.md`)을 갱신하여 인지시킴. |
