# Implementation Plan: Frontend Chart & Screener (Next.js)

## Overview
백엔드 통합 차트 API(`Top Volume`, `Chart Data`)를 호출하여 화면에 렌더링하는 Next.js 프론트엔드 애플리케이션을 구축합니다. `shadcn/ui`를 활용해 빠르고 깔끔한 화면을 구성하며, `lightweight-charts`를 사용해 1분봉 데이터를 기반으로 한 멀티 타임프레임(5분, 15분 등) 캔들 차트 및 10개의 다중 주기 이동평균선(MA)을 렌더링합니다.

## Architecture Decisions
- **Client-side Data Aggregation**: 백엔드는 1분봉 Raw 데이터만 내려주고, 사용자가 프론트엔드에서 '5분봉', '15분봉' 탭을 클릭할 때 프론트엔드 메모리 상에서 즉각적으로 캔들을 그룹핑(병합)하여 차트에 반영합니다. (서버 통신 최소화)
- **Separate Series Rendering**: `lightweight-charts`의 특징을 살려 주축인 `CandlestickSeries`의 Timeframe이 변하더라도, 10개의 장단기 이평선(`LineSeries`)은 1분 단위의 세밀한 원본 값을 그대로 그려내어 차트의 정밀도를 유지합니다.
- **Component Isolation**: 차트 인스턴스 생성 및 파괴를 관리하는 순수 래퍼 컴포넌트(`LightweightChart.tsx`)와, 비즈니스 로직(데이터 페칭, 타임프레임 변환)을 담당하는 컨테이너(`ChartContainer.tsx`)를 분리합니다.

## Task List

### Phase 1: Foundation (API Client & Aggregation Utils)
- [ ] Task 1: 백엔드(FastAPI) 통신을 위한 API 클라이언트 작성 (`lib/api.ts`)
- [ ] Task 2: 1분봉 OHLCV 데이터를 N분봉으로 병합(Grouping)하는 유틸리티 함수 구현 (`lib/chart-utils.ts`)

### Checkpoint: Foundation
- [ ] 유틸리티 함수의 병합 결과(시가, 고가, 저가, 종가, 누적 거래량)가 정확한지 단위 테스트 또는 수동 콘솔 로그 확인

### Phase 2: Core Chart Rendering (Lightweight Charts)
- [ ] Task 3: `lightweight-charts` 기본 캔들 차트 컴포넌트 마운트/언마운트 구현 (`components/chart/LightweightChart.tsx`)
- [ ] Task 4: 10개의 장단기 이평선(ma3 ~ ma_daily_200)을 `LineSeries`로 추가하고 색상/두께를 다르게 렌더링
- [ ] Task 5: 캔들 데이터와 이평선 데이터를 주입하고, Timeframe(1m, 5m, 15m) 변경 시 차트를 업데이트하는 상위 컨테이너 구현 (`components/chart/ChartContainer.tsx`)

### Checkpoint: Core Features
- [ ] 차트가 정상적으로 렌더링되며, 5분/15분봉 버튼 클릭 시 캔들이 즉각적으로 변환되는지 확인
- [ ] 모든 이평선이 차트에 잘 오버레이 되는지 확인

### Phase 3: Screener & App Routing (Shadcn UI)
- [ ] Task 6: 메인 페이지(`/`)에 `shadcn/ui`의 Table 컴포넌트를 이용한 거래량 상위 30종목 스크리너 뷰 구현
- [ ] Task 7: 스크리너의 종목 행(Row) 클릭 시 해당 종목의 차트 페이지(`/chart/[ticker]`)로 이동하는 라우팅 추가
- [ ] Task 8: 차트 페이지에 이평선(MA) on/off 토글 버튼(가시성 제어) 추가 (선택 사항: 10개가 한 번에 보이면 복잡하므로)

### Checkpoint: Complete
- [ ] 메인 페이지 ➡️ 차트 페이지 진입 플로우 정상 동작
- [ ] Vercel 등 배포 전 `npm run build` 에러 없음 확인

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 클라이언트 캔들 병합 연산 부하 | Med | 최근 3영업일 수준의 1분봉(약 1200개) 연산은 브라우저에서 1ms 이내로 처리되므로 `useMemo`를 통해 불필요한 재연산만 방지 |
| Resize Observer 메모리 누수 | High | `lightweight-charts` 사용 시 창 크기 변경에 대응하는 ResizeObserver를 `useEffect`의 cleanup에서 확실히 해제(disconnect) 및 차트 `remove()` 호출 |
| 이평선 범례(Legend) 공간 부족 | Low | 차트 좌측 상단에 HTML Overaly 형식으로 현재 마우스 호버 지점의 이평선 값을 텍스트로 보여주는 플러그인/HTML 추가 |

## Open Questions
- 백엔드 주소(CORS 설정 및 포트 번호)가 환경변수로 잘 주입되는지 확인이 필요합니다. (보통 로컬에서 FastAPI는 8000, Next.js는 3000을 씁니다)
