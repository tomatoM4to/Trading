# Implementation Plan: Screener Result Enrichment

## Overview
스크리너 연산 결과(티커 리스트)에 직관적인 판단을 돕는 리치 데이터(시장, 시가총액, 현재가, 거래대금, 전일대비 등락률)를 추가하여 UI에 표시합니다. 프론트엔드와 백엔드가 나누어진 구조이므로, API 응답 스키마 변경부터 프론트엔드 UI 렌더링까지 엔드투엔드(End-to-End) 수직 분할(Vertical Slicing) 방식으로 계획을 수립합니다.

## Architecture Decisions
- **Zero-Latency 유지**: 쿼리 최적화를 위해 복잡한 연산 없이 `stock_codes` (PK), `minute_ohlcv` (PK 인덱스 역순), `daily_ohlcv` (PK 인덱스 역순) 테이블을 티커 기준으로 단순 조회(또는 서브쿼리 조인)하여 연산 부하를 최소화합니다.
- **백엔드에서 등락률 연산**: 프론트엔드의 부담을 줄이고 스키마의 직관성을 높이기 위해, 백엔드에서 `(현재가 - 전일종가) / 전일종가 * 100`을 계산하여 `change_rate` 필드로 반환합니다.
- **UI 시각화 최적화**: 거래대금과 시가총액은 큰 숫자이므로 프론트엔드에서 한국어 단위(예: "5,200억")로 포맷팅하여 가독성을 높이고, 등락률은 양수(빨간색)/음수(파란색)로 색상을 적용합니다.

## Task List

### Phase 1: Backend API Enrichment
- [ ] Task 1: API 스키마 및 서비스 로직 업데이트

### Checkpoint: Backend Complete
- [ ] 스웨거(Swagger) 또는 직접 API 호출 시 `change_rate`, `amount` 등 신규 필드가 정상적으로 반환되는가?
- [ ] 쿼리 속도 저하(수 초 이상의 딜레이)가 없는가?

### Phase 2: Frontend UI Implementation
- [ ] Task 2: 프론트엔드 인터페이스 및 테이블 컴포넌트 업데이트

### Checkpoint: Complete
- [ ] 스크리너 실행 후 테이블에 신규 컬럼들이 정상적으로 표시되는가?
- [ ] 데이터 포맷(억 단위, 등락률 색상)이 기획대로 렌더링되는가?
- [ ] Ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| DB 락 또는 지연 | High | 서브쿼리에 반드시 인덱스를 타도록 `ORDER BY date DESC LIMIT 1` 구조 유지 |
| 장 시작 전 데이터 부족 | Med | `minute_ohlcv`에 오늘 데이터가 없을 경우 에러가 나지 않도록 `LEFT JOIN` 또는 `IS NULL` 처리 보완 |
| UI 가로 스크롤/공간 부족 | Low | 컬럼 너비를 유동적으로 조절하고 Tailwind `truncate` 적용 |

## Open Questions
- 등락률(`change_rate`)을 소수점 둘째 자리에서 반올림하여 넘겨주는 것이 좋겠죠? (백엔드에서 `round()` 처리)
