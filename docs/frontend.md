# 프론트엔드 대시보드

## 기술 구성

- Next.js 16 App Router
- React 19, TypeScript
- Tailwind CSS 4
- shadcn/ui와 Base UI
- Lightweight Charts 5
- `@microsoft/fetch-event-source` 기반 SSE

프론트엔드 작업 전에는 `web/AGENTS.md`의 지시에 따라 설치된 Next.js 문서를 확인한다. 학습 데이터의 이전 Next.js 관례를 그대로 적용하지 않는다.

## 페이지 구조

| 경로 | 구성 |
|---|---|
| `/` | `ScreenerBuilder` 중심의 스크리너 화면 |
| `/chart/[ticker]` | 개별 종목 전체 차트 화면 |

`ChartModal`은 스크리너 결과 행을 선택했을 때 동일한 차트 컴포넌트를 대화상자에 표시한다.

## 스크리너 UI

`ScreenerBuilder`는 필터 블록과 AND/OR 연산자를 로컬 state로 관리한다. 실행 전에 UI 파라미터를 백엔드 AST로 변환한다.

- 시간 프레임에 따라 `ma5` 또는 `ma_daily_5` 형태로 변환
- 문자열 입력 기간·임계값은 `Number()`로 변환
- 투자자 랭킹 limit은 30으로 고정
- SSE의 start/progress/complete/error 이벤트로 필터 상태와 결과 갱신
- complete/error에서 스트림 Abort

결과 테이블은 기본 보기와 필터별 `filter_values`를 이용한 랭킹 보기를 제공한다.

## 차트 데이터 흐름

`web/lib/api.ts`는 `NEXT_PUBLIC_API_URL` 또는 `http://localhost:8000`을 기준으로 `/market/chart/{ticker}`를 호출한다.

`ChartContainer`는 선택한 시간 프레임에 따라 다음 데이터를 요청한다.

- 1m, 3m, 5m, 15m, 30m, 1h: `type=minute`
- 1D, 1W, 1M: `type=daily`

서버는 원시 1분봉 또는 일봉을 반환한다. 3~60분봉과 주봉·월봉 집계는 `web/lib/chart-utils.ts`에서 클라이언트가 수행한다. MA 선도 선택한 시간 프레임에 맞춰 클라이언트에서 매핑한다.

지원 MA는 5, 10, 20, 60, 120, 200이다.

## 타입 계약

`web/types/market.ts`가 차트 응답 타입을 정의한다. 스크리너 요청·응답 타입은 `ScreenerBuilder`와 관련 컴포넌트에 정의돼 있다.

백엔드 스키마를 바꿀 때는 다음을 함께 확인한다.

1. `app/schemas/` Pydantic 모델
2. `web/types/` 또는 컴포넌트 로컬 타입
3. `web/lib/api.ts`
4. 차트 aggregation과 필터 payload 변환

## UI 원칙

- 모바일과 데스크톱에서 필터·차트가 사용할 수 있어야 한다.
- 로딩, 오류, 빈 결과 상태를 명시한다.
- 색상만으로 필터 진행 상태나 차트 의미를 전달하지 않는다.
- 클라이언트 집계는 단일 종목 데이터에 한정한다.
- 브라우저에 KIS 인증 정보나 관리자 비밀값을 전달하지 않는다.

## 검증

```powershell
cd web
npm run lint
npx tsc --noEmit
npm run build
```

차트나 인터랙션 변경은 실제 브라우저에서 콘솔 오류, 네트워크 요청, 작은 화면과 큰 화면을 함께 확인한다.
