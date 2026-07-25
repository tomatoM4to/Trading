# Implementation Plan: Perfect Time Synchronization for Chart Indicators

## Overview
이 계획은 Lightweight Charts에서 발생하는 '이평선이 캔들 이후 허공으로 뻗어 나가는(미래로 그려지는)' 렌더링 버그를 근본적으로 해결하기 위한 "정면돌파(Perfect Time Synchronization)" 구현안입니다. 사용자가 선택한 타임프레임(예: 30분, 일봉)에 맞춰 이평선(LineSeries)의 타임스탬프를 캔들(CandlestickSeries)과 완벽하게 일치하도록 그룹핑(Aggregation)하여 제공합니다. 이를 통해 '할 수 있는데 끄는 것'의 자유도를 사용자에게 제공합니다.

## Architecture Decisions
- **LineSeries Aggregation 적용**: `CandlestickSeries`와 `LineSeries`가 동일한 타임프레임 척도를 공유하도록 `extractLineSeriesData` 함수를 전면 재작성합니다.
- **마지막 유효 값 유지**: 특정 시간 단위(예: 30분 구간) 내의 이평선 값들 중 가장 '마지막' 시점의 유효한 값을 해당 캔들의 이평선 값으로 대표하여 사용합니다.
- **프론트엔드 유틸리티 내 격리**: 백엔드 API 변경 없이 순수하게 프론트엔드 데이터 가공 레이어(`chart-utils.ts`)에서만 해결하여 부작용(Side Effect)을 최소화합니다.

## Task List

### Phase 1: Data Utility Layer
- [ ] **Task 1: `extractLineSeriesData` 리팩토링**
  - **Description**: 이평선 추출 로직이 타임프레임을 인식하고 캔들과 완벽하게 동일한 기준의 타임스탬프를 생성하도록 수정합니다.
  - **Acceptance criteria**:
    - [ ] `extractLineSeriesData` 함수가 세 번째 파라미터로 `timeframe: string`을 받도록 시그니처 변경.
    - [ ] 타임프레임이 일봉(1D/1W/1M) 계열일 때와 분봉(1~60) 계열일 때의 그룹핑 기준 시간이 `aggregateCandles` 및 `aggregateDailyCandles`와 정확히 일치.
    - [ ] 각 시간 그룹 내에서 가장 최신의(마지막) `value`를 추출하여 반환.

### Phase 2: UI Component Layer
- [ ] **Task 2: `ChartContainer` 업데이트**
  - **Description**: 추출 유틸리티의 변경된 인터페이스에 맞게 UI 컴포넌트 측의 호출 로직을 수정합니다.
  - **Acceptance criteria**:
    - [ ] `useMemo`를 통한 `lineData` 계산 로직에 `timeframe` 파라미터 주입.
    - [ ] `useMemo` 의존성 배열에 `timeframe` 추가.

### Checkpoint: Complete
- [ ] 30분봉(30m) 차트 등에서 캔들이 끝남과 동시에 이평선도 정확히 끝나는지(허공으로 뻗어나가지 않는지) 확인.
- [ ] 일봉(1D) 차트에서 분봉 이평선(1m, 3m 등)이 캔들에 맞춰 올바르게 렌더링되는지 확인.
- [ ] 차트 하단의 시간축(X-axis)에 00:05, 00:10 등 엉뚱한 미래 시간이 나타나지 않고 깔끔하게 렌더링되는지 확인.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 로컬 타임존 변환 오차 | High | `dateObj.getTime() / 1000` 로직과 `Date.getDay()` 등의 네이티브 날짜 처리 함수가 KST와 완벽히 동기화되는지 집중 검증 |
| 연산 성능 저하 | Low | 3일치 분봉 데이터(약 1200개) 순회 및 그룹핑은 모던 브라우저에서 1ms 미만 소요되므로 성능 이슈 없음 |
