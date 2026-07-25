## Task 1: API 클라이언트 작성 (`lib/api.ts`)

**Description:** FastAPI 서버(`http://localhost:8000`)와 통신하여 `TopVolumeResponse` 및 `ChartDataResponse` 데이터를 가져오는 fetch 기반 API 클라이언트를 작성합니다.

**Acceptance criteria:**
- [ ] `getTopVolume()` 함수 구현 (GET `/market/screener/top-volume`)
- [ ] `getChartData(ticker, days)` 함수 구현 (GET `/market/chart/{ticker}?days={days}`)
- [ ] API 응답 타입 인터페이스 선언 (`ChartDataPoint` 등)

**Verification:**
- [ ] 수동 체크: 프론트엔드 콘솔에 데이터가 정상적으로 찍히는지 확인

**Dependencies:** None

**Files likely touched:**
- `web/lib/api.ts`
- `web/types/market.ts` (타입 정의용)

**Estimated scope:** Small: 1-2 files

---

## Task 2: 1분봉 OHLCV 병합(Grouping) 유틸리티 함수 구현

**Description:** API로 받은 1분봉 배열을 5분, 15분 단위의 배열로 변환하는 순수 JS 함수를 작성합니다. 시간 단위를 쪼개어 시가(첫 캔들), 고가(최대), 저가(최소), 종가(마지막 캔들), 거래량(합계)을 계산합니다.

**Acceptance criteria:**
- [ ] `aggregateCandles(data: ChartDataPoint[], minutes: int)` 함수 구현
- [ ] 각 시간 구간(예: 09:00~09:04)의 데이터를 1개의 캔들로 병합

**Verification:**
- [ ] 수동 체크: 더미 데이터를 넣고 5분 단위 병합 결과가 정확한지 확인

**Dependencies:** None

**Files likely touched:**
- `web/lib/chart-utils.ts`

**Estimated scope:** Small: 1 file

---

## Checkpoint: Foundation
- [ ] 유틸리티 함수의 병합 결과가 정확한지 확인

---

## Task 3 & 4: LightweightChart 래퍼 컴포넌트 및 MA 추가

**Description:** `lightweight-charts` 라이브러리를 초기화하고, `CandlestickSeries` 1개와 `LineSeries` 10개(단기/장기 이평선)를 생성하는 핵심 뷰포트 컴포넌트를 작성합니다.

**Acceptance criteria:**
- [ ] `div` 컨테이너에 `createChart` 초기화 및 `useEffect` 클린업 로직 추가
- [ ] `addCandlestickSeries`로 캔들 객체 주입
- [ ] `addLineSeries`로 10개의 이평선을 각각 다른 색상/두께로 주입

**Verification:**
- [ ] 컴포넌트 마운트 시 브라우저에 빈 차트 그리드가 에러 없이 나타나는지 확인

**Dependencies:** None

**Files likely touched:**
- `web/components/chart/LightweightChart.tsx`

**Estimated scope:** Medium: 1-2 files

---

## Task 5: ChartContainer 컴포넌트 구현 (상태 관리)

**Description:** API 데이터를 Fetch하고, 사용자가 선택한 타임프레임(1m, 5m, 15m 등)에 따라 데이터를 가공한 뒤 `LightweightChart`에 Props로 내려주는 상태 관리 컨테이너를 구현합니다. Shadcn UI의 ToggleGroup을 사용해 타임프레임을 변경합니다.

**Acceptance criteria:**
- [ ] `useQuery` 또는 `useEffect`를 사용한 데이터 페칭
- [ ] 타임프레임 선택 UI (1분, 3분, 5분, 15분, 30분, 1시간)
- [ ] 10개의 이평선 체크박스(가시성 On/Off 토글) 추가

**Verification:**
- [ ] 버튼 클릭 시 차트 캔들이 즉각적으로 변환되는지 확인

**Dependencies:** Task 1, Task 2, Task 3

**Files likely touched:**
- `web/components/chart/ChartContainer.tsx`

**Estimated scope:** Medium: 3 files

---

## Checkpoint: Core Features
- [ ] 차트 정상 렌더링 및 이평선 오버레이 동작 확인

---

## Task 6: 메인 스크리너 페이지 구현 (`app/page.tsx`)

**Description:** FastAPI의 `Top Volume` API를 호출하여 거래량 상위 30개 종목을 표(Table) 형태로 렌더링합니다. Shadcn UI의 `Table` 컴포넌트를 활용합니다.

**Acceptance criteria:**
- [ ] 거래량 상위 종목 리스트 페칭 및 렌더링
- [ ] 테이블 디자인 (단축코드, 종목명, 거래량 컬럼)

**Verification:**
- [ ] `http://localhost:3000/` 접속 시 목록이 렌더링되는지 확인

**Dependencies:** Task 1

**Files likely touched:**
- `web/app/page.tsx`

**Estimated scope:** Small: 1 file

---

## Task 7: 동적 차트 라우팅 구현 (`app/chart/[ticker]/page.tsx`)

**Description:** 스크리너 테이블의 행을 클릭하면 `/chart/[ticker]` 경로로 이동하고, 해당 종목의 코드를 읽어와 `ChartContainer` 컴포넌트를 렌더링하는 동적 라우트 페이지를 구성합니다.

**Acceptance criteria:**
- [ ] `next/link` 또는 `useRouter`를 통해 스크리너 테이블 행에 클릭 이벤트 추가
- [ ] `app/chart/[ticker]/page.tsx` 파일 생성 및 `ChartContainer` 주입

**Verification:**
- [ ] 테이블 항목 클릭 시 화면이 전환되며 해당 종목의 차트가 정상적으로 그려지는지 테스트

**Dependencies:** Task 5, Task 6

**Files likely touched:**
- `web/app/page.tsx`
- `web/app/chart/[ticker]/page.tsx`

**Estimated scope:** Small: 2 files
