# Spec: Screener Ranking View (Multi-Factor)

## Objective
스크리너 다중 지표(Multi-Factor) 교집합 검색 결과를 트레이더가 직관적으로 비교할 수 있도록 프론트엔드에 **'랭킹 뷰(Ranking View)'**를 도입합니다. 백엔드 수급 필터의 순위 반환 로직을 개선하고, 프론트엔드는 각 필터별 고유한 정렬 기준을 적용하여 개별 정수 순위(Rank)와 이를 종합한 최종 평균 순위를 산출하여 동적 테이블로 렌더링합니다.

## Tech Stack
- **Backend**: FastAPI, Python 3.12, SQLite
- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, shadcn/ui

## Commands
- Backend Dev: `uv run fastapi dev app/main.py`
- Frontend Dev: `cd web && npm run dev`
- Backend Lint: `uv run ruff check . --fix && uv run ruff format .`

## Project Structure
- `app/services/screener_service.py` → 백엔드 수급 API 순위 반환 로직 수정 영역
- `web/components/screener/ScreenerResultTable.tsx` → 프론트엔드 랭킹 뷰 UI 및 동적 정렬 로직 구현 영역

## Code Style
**Frontend Dense Ranking Logic (Example)**
```typescript
// 점수에 따라 순위를 매길 때 동점자는 같은 순위를 부여합니다.
function computeRanks(items: ResultItem[], filterId: string, sortType: 'asc' | 'desc') {
  const sorted = [...items].sort((a, b) => {
    const valA = a.filter_values[filterId] ?? 0;
    const valB = b.filter_values[filterId] ?? 0;
    return sortType === 'asc' ? valA - valB : valB - valA;
  });
  
  let currentRank = 1;
  let previousValue = sorted[0]?.filter_values[filterId];
  
  sorted.forEach((item, index) => {
    const val = item.filter_values[filterId];
    if (val !== previousValue) {
      currentRank = index + 1; // Standard Competition Ranking (1, 1, 3)
      previousValue = val;
    }
    item.ranks[filterId] = currentRank;
  });
}
```

## Testing Strategy
- **Backend**: `scripts/benchmark_screener.py`를 활용해 외국인/기관 필터가 포함된 `Heavy 5` 시나리오 호출 시, `filter_values` 내 수급 순위가 0.0이 아닌 1.0~30.0으로 반환되는지 검증.
- **Frontend**: 브라우저에서 스크리너 파이프라인 완료 후 '랭킹 뷰' 토글 시 컬럼들이 정상적으로 렌더링되고 평균 순위 기준으로 정렬되는지 시각적 검증.

## Boundaries
- **Always**: 동점자(Tie) 발생 시 동일한 순위를 부여하고, 그 평균치 계산 시 공평성을 유지할 것.
- **Ask first**: 팩터별 임의의 가중치(Weight)를 부여하는 기능 추가 시 설계 승인을 받을 것. (현재는 무조건 1:1 단순 평균)
- **Never**: 백엔드에서 정렬을 억지로 묶어버리는 하드코딩. (정렬 렌더링은 무조건 프론트엔드 위임)

## Success Criteria
1. **백엔드 패치**: `foreign_net_buy_rank` 및 `inst_net_buy_rank` 필터가 `{"filter_id": 1.0}` 형태로 순위 점수를 제공한다.
2. **UI 토글 기능**: `ScreenerResultTable`에 '기본 뷰 / 랭킹 뷰' 토글 버튼이 존재한다.
3. **개별 순위 산출**: 
   - `ma_alignment` (이격도 편차율) -> **오름차순 (낮은게 1위)**
   - `ma_cross` (교차 폭) -> **내림차순 (높은게 1위)**
   - `ma_convergence_*` (수렴 오차율) -> **오름차순 (낮은게 1위)**
   - `*_net_buy_rank` (수급 랭킹) -> **오름차순 (낮은게 1위)**
4. **최종 정렬**: 각 필터별 순위의 산술 평균(Average Rank)이 우측 끝 컬럼에 표기되고, 이 평균값이 가장 낮은(1위에 가까운) 순서대로 전체 행이 오름차순 정렬된다.

## Open Questions
- 없음 (인터뷰를 통해 모두 해소됨)
