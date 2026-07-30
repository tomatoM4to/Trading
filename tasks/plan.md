# Implementation Plan: Smart Moving Averages Toggle

## Overview
현재 프론트엔드의 차트 뷰어에서 제공되는 이동평균선(MA) 종류를 표준에 맞게 재정의하고, 타임프레임(분봉/일봉) 전환 시 사용자 인터페이스에 '스마트 디폴트(Smart Defaults)' 기능을 도입하여 알맞은 이평선이 자동으로 켜지도록 구성합니다.

## Architecture Decisions
- **백엔드/프론트엔드 동기화**: 백엔드 SQLite 윈도우 함수에서 새롭게 정의된 분봉/일봉 이평선(5, 10, 20, 60, 120 등)을 쿼리하도록 수정하고, 이를 Pydantic 모델과 프론트엔드 타입스크립트 인터페이스에 동일하게 반영합니다.
- **Smart Defaults UI**: `ChartContainer.tsx`에서 타임프레임 변경 이벤트(`isDailyTF` 플래그)를 감지하는 `useEffect`를 추가하여, 타임프레임 성격에 맞지 않는 이평선들을 자동 Off하고 맞는 이평선들을 자동 On하도록 상태(`visibleMAs`)를 덮어씌웁니다.

## Task List

### Phase 1: Foundation (Backend)
- [ ] Task 1: `app/schemas/market.py`의 `ChartDataPoint` 모델에서 MAs 필드를 표준(분봉: 1, 5, 10, 20, 60, 120 / 일봉: 1, 5, 20, 60, 120)으로 수정
- [ ] Task 2: `app/services/market_service.py` 내의 `get_chart_data` 쿼리 수정 (SQLite `AVG() OVER()` 윈도우 함수의 ROWS 개수 조정)

### Phase 2: Core Features (Frontend)
- [ ] Task 3: `web/types/market.ts` 내의 `ChartDataPoint` 타입스크립트 인터페이스를 백엔드와 일치되게 갱신
- [ ] Task 4: `web/components/chart/LightweightChart.tsx` 내의 `MA_CONFIGS` 설정을 새 기준에 맞게 변경하고 1m/1d 는 (Debug) 명칭 부여
- [ ] Task 5: `web/components/chart/ChartContainer.tsx` 내에 타임프레임 전환 감지 자동 토글(Smart Default) `useEffect` 로직 추가

### Checkpoint: Complete
- [ ] 타임프레임 변경 시 이평선 버튼들이 자동으로 On/Off 됨
- [ ] 백엔드와 프론트엔드 간 타입이 완벽히 동기화됨

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 프론트/백 타입 불일치 | High | 백엔드 모델과 프론트 타입을 동일한 Pull Request(또는 턴)에서 동시 업데이트 |
| SQLite 쿼리 오타 | Med | 윈도우 함수 `ROWS BETWEEN n PRECEDING` 값을 정확히 n-1 로 할당하여 검증 |
