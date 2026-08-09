# ADR-029: 차트 API MA200 지원 및 디버그 이평선 제거

## Status
Accepted

## Date
2026-08-10

## Context
기존 시스템에서 백그라운드 스케줄러(MACalculator)와 인메모리 스키마(`daily_ma`, `minute_ma`)는 `ma200`을 완벽하게 지원하고 스크리너 엔진에서도 활용하고 있었으나, **프론트엔드의 차트 뷰(Chart View)** API(`get_chart_data`)는 `ma120`까지만 하드코딩된 윈도우 함수(`AVG(...) OVER ...`)를 사용하여 200일선/200분선이 차트에 그려지지 않는 문제가 있었습니다.
또한, 프론트엔드 차트 컴포넌트에는 디버깅 목적으로 삽입되었던 `1m`(`ma1`) 및 `1d`(`ma_daily_1`) 지표가 남아있어 사용자 UI에 혼란을 주고 있었습니다.

## Decision
1. **차트 API 동기화 (SQL Push-down 확장)**: 
   - `app/services/market_service.py` 내의 일봉 및 분봉 차트 반환용 SQL 쿼리에 `ma200` 및 `ma_daily_200` 산출 로직(`ROWS BETWEEN 199 PRECEDING AND CURRENT ROW`)을 명시적으로 추가했습니다.
   - Pydantic 모델(`ChartDataPoint`)에도 해당 필드를 추가하여 200기간 이평선을 공식적으로 프론트엔드에 전달합니다.
2. **프론트엔드 UI 정리 (디버그 라인 제거)**:
   - `LightweightChart.tsx` 및 `ChartContainer.tsx`에서 불필요한 `1m`, `1d` 이평선 렌더링 코드를 제거했습니다.
3. **스크리너 UI 업데이트**:
   - `FilterBlock.tsx`에서 이평선 다중 선택 및 드롭다운 목록에 `200` 옵션을 추가하여, 사용자가 스크리너에서도 명시적으로 200일선/200분선 필터링을 조작할 수 있도록 했습니다.

## Consequences
- 프론트엔드와 백엔드 간의 이동평균선 스펙이 완전히 동기화되었습니다 (5, 10, 20, 60, 120, 200 지원).
- 200 기간 윈도우 함수 연산이 차트 단일 종목 API에서 추가로 실행되지만, 1개 종목에 대한 연산이므로 1GB RAM 환경에서도 OOM이나 심각한 레이턴시 저하를 유발하지 않음을 확인했습니다.
- 불필요한 디버그 지표를 삭제하여 차트 UI가 훨씬 깔끔해졌습니다.
