# Frontend Specifications

## Overview
Trading Server 프로젝트의 프론트엔드는 KIS OpenAPI를 통해 백엔드가 수집 및 가공한 2,400여 개 전 종목의 주가 데이터를 시각화하고, 차트 분석 기능을 제공하기 위한 사용자 인터페이스입니다. 
초기에는 백엔드(FastAPI)와 통합된 구조였으나, 독립적인 배포 및 최적화를 위해 Next.js 15+ 환경의 별도 프로젝트(`/web` 디렉토리)로 분리되었습니다.

## Tech Stack
- **Framework**: Next.js (App Router 기반)
- **Language**: TypeScript
- **Styling**: Tailwind CSS, shadcn/ui
- **Charting**: Lightweight Charts (TradingView)
- **Data Fetching**: React Server Components (RSC) 및 Next.js fetch API

## Architecture Principles

### 1. Client-Side Aggregation (백엔드 부하 최소화)
백엔드가 호스팅되는 서버가 Oracle Cloud 1 OCPU / 1GB RAM의 극도로 제한된 환경임을 고려하여, 데이터 그룹핑 연산은 100% 클라이언트(브라우저) 사이드에서 처리합니다.
- **분봉 변환**: 백엔드는 1분봉 원본 데이터만 제공(`type=minute`)하며, 프론트엔드의 `aggregateCandles` 유틸리티가 이를 3m, 5m, 15m, 30m, 60m 캔들로 변환합니다.
- **일봉/주봉/월봉 변환**: 백엔드는 일봉 원본 데이터만 제공(`type=daily`)하며, 프론트엔드의 `aggregateDailyCandles` 유틸리티가 이를 주봉(1W), 월봉(1M)으로 그룹핑합니다.

### 2. Perfect Time Synchronization (차트 렌더링 최적화)
차트의 X축(Time Scale) 오류를 방지하기 위해, 모든 이동평균선(LineSeries) 데이터는 캔들(CandlestickSeries)과 완벽하게 동일한 기준 시각으로 동기화됩니다.
- 캔들의 타임프레임(예: 30분봉)에 맞춰 이평선 데이터를 동일 구간으로 슬라이싱합니다.
- 구간 내의 **가장 마지막 유효한 값**을 추출하여 해당 캔들과 정확히 일치하는 타임스탬프로 차트에 삽입합니다.
- 관련 ADR: `docs/decisions/ADR-011-chart-perfect-time-synchronization.md`

### 3. Smart Default UI (이평선 자동 토글)
차트 가독성과 스케일 왜곡을 방지하기 위해, 사용자가 선택한 타임프레임(분봉 vs 일봉)에 맞춰 관련 이동평균선(MA) 체크박스가 자동으로 On/Off 되는 스마트 디폴트 로직이 적용되어 있습니다.
- **UI 간소화 (Abstract Indicators)**: "5m", "5d" 등의 문자열 대신 "5, 10, 20, 60, 120, 200" 형태의 직관적인 숫자 레이블만을 UI에 노출하며, 상태 변경 시 내부적으로 분봉/일봉(`ma` vs `ma_daily`) 키를 자동 라우팅합니다. (백엔드 호환성을 위해 10일선 `ma_daily_10` 추가 지원)
- **분봉(1m~60m) 선택 시**: 분봉 이평선 자동 매핑 및 On, 일봉 이평선 자동 Off
- **일봉(1D~) 선택 시**: 일봉 이평선 자동 매핑 및 On, 분봉 이평선 자동 Off
- 관련 ADR: `docs/decisions/ADR-013-smart-default-moving-averages.md`

## UI & Layout Structure

### 1. Dark Mode & Aesthetics
프로젝트의 UI는 "Wow" 팩터를 주기 위해 프리미엄 금융 플랫폼 스타일을 지향합니다.
- Tailwind CSS의 다크모드를 기본(Default)으로 채택.
- 미세한 마이크로 애니메이션과 반응형(Hover) 피드백 적용.
- 차트 컬러는 한국식 증권 기준 적용 (상승: Red `#ef5350`, 하락: Blue `#26a69a`).

### 2. Mobile-First & Modal Optimization
모바일 환경에서 차트의 사용성과 공간 효율을 극대화하기 위해 다음 패턴을 지향합니다.
- **ResizeObserver 적용 (Lightweight Charts v5)**: `window.resize` 이벤트 대신 `ResizeObserver`를 활용하여 모바일 뷰포트나 부모 DOM의 유동적인 크기 변화에 차트가 유연하게(100% height/width) 대응합니다.
- **Double-border 최소화**: 모달(`DialogContent`) 안에서 차트 컨테이너를 띄울 때 중복된 `<Card>` 테두리와 패딩을 제거하고 순수 레이아웃(`div`)으로만 렌더링하여 좁은 화면의 낭비를 방지하고, 닫기(`X`) 버튼을 자연스럽게 헤더 우측 상단에 정렬시킵니다.

### 3. Component Organization (`/web/components`)
- **`chart/ChartContainer.tsx`**: 상태 관리(Timeframe, MA Visibility) 및 `LightweightChart` 컴포넌트 래퍼 역할을 담당합니다. `useMemo`를 통해 Aggregation 및 Line Series 추출 로직을 수행합니다.
- **`chart/LightweightChart.tsx`**: 순수하게 UI를 렌더링하는 View 컴포넌트로, 데이터가 변경될 때마다 차트를 갱신(Update)하거나 인스턴스를 관리합니다.
- **`screener/ScreenerBuilder.tsx` & `ScreenerResultTable.tsx`**: 다중 필터 AST 작성 및 SSE 스트림 렌더링. `@microsoft/fetch-event-source`를 통해 백엔드의 진행 상황(Progress Event)을 받아 실시간으로 개별 `FilterBlock`의 상태(Loader/Check)를 업데이트하고 남은 종목 수를 표시하는 점진적(Progressive) UX를 제공합니다. 연산 완료 시, 백엔드로부터 전달받은 `filter_values` (다중 지표 점수 딕셔너리)를 기반으로 **Client-Side 동적 정렬 (Multi-Factor Ranking)** 기능을 수행합니다. 기본 뷰 외에도 각 필터별 고유한 정렬 기준을 적용하여 개별 순위를 산출하고, 이를 종합한 평균 순위(Average Rank)로 렌더링하는 **랭킹 뷰(Ranking View)**를 제공합니다.

## Data Flow
1. 사용자가 페이지(예: `/chart/005930`) 접속.
2. 현재 `timeframe` 상태(예: `30` 또는 `1D`)에 따라 `fetch` 로직이 API 호출:
   - 분봉(1~60)일 경우: `/api/market/chart/005930?type=minute`
   - 일봉 이상(1D, 1W, 1M)일 경우: `/api/market/chart/005930?type=daily`
3. 반환된 Raw Data는 `ChartContainer` 내에서 `aggregateCandles`, `aggregateDailyCandles`, `extractLineSeriesData`를 거쳐 렌더링 포맷으로 변환됩니다.
4. 변환된 `candleData` 및 `lineData` Props가 `LightweightChart`에 전달되어 화면에 표시됩니다.
