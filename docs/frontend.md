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

## UI & Layout Structure

### 1. Dark Mode & Aesthetics
프로젝트의 UI는 "Wow" 팩터를 주기 위해 프리미엄 금융 플랫폼 스타일을 지향합니다.
- Tailwind CSS의 다크모드를 기본(Default)으로 채택.
- 미세한 마이크로 애니메이션과 반응형(Hover) 피드백 적용.
- 차트 컬러는 한국식 증권 기준 적용 (상승: Red `#ef5350`, 하락: Blue `#26a69a`).

### 2. Component Organization (`/web/components`)
- **`chart/ChartContainer.tsx`**: 상태 관리(Timeframe, MA Visibility) 및 `LightweightChart` 컴포넌트 래퍼 역할을 담당합니다. `useMemo`를 통해 Aggregation 및 Line Series 추출 로직을 수행합니다.
- **`chart/LightweightChart.tsx`**: 순수하게 UI를 렌더링하는 View 컴포넌트로, 데이터가 변경될 때마다 차트를 갱신(Update)하거나 인스턴스를 관리합니다.

## Data Flow
1. 사용자가 페이지(예: `/chart/005930`) 접속.
2. 현재 `timeframe` 상태(예: `30` 또는 `1D`)에 따라 `fetch` 로직이 API 호출:
   - 분봉(1~60)일 경우: `/api/market/chart/005930?type=minute`
   - 일봉 이상(1D, 1W, 1M)일 경우: `/api/market/chart/005930?type=daily`
3. 반환된 Raw Data는 `ChartContainer` 내에서 `aggregateCandles`, `aggregateDailyCandles`, `extractLineSeriesData`를 거쳐 렌더링 포맷으로 변환됩니다.
4. 변환된 `candleData` 및 `lineData` Props가 `LightweightChart`에 전달되어 화면에 표시됩니다.
