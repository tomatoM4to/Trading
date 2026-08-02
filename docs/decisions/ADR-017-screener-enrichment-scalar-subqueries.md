# ADR-017: Screener Result Enrichment via Scalar Subqueries

## Status
Accepted

## Date
2026-08-02

## Context
스크리너 연산을 통해 2,400개 종목 중 조건에 부합하는 소수의 종목(Result Set)이 도출된 후, 프론트엔드 UI에 직관적인 판단 근거(시장, 현재가, 당일 거래대금, 시가총액, 전일 대비 등락률)를 제공해야 했습니다.
1GB RAM 환경에서는 추가적인 무거운 조인(JOIN)이나 KIS API 추가 호출이 불가능하며, `daily_ohlcv`와 `minute_ohlcv`의 데이터 갱신 시점(스케줄러 동작 시간)이 다르기 때문에 전일 종가를 구하는 로직에 예외가 발생할 위험이 있었습니다.

## Decision
- 결과 집합(Set)에 포함된 티커들을 대상으로 `stock_codes` 테이블을 조회하되, **스칼라 서브쿼리(Scalar Subquery)**를 SELECT 절에 포함하여 `minute_ohlcv`와 `daily_ohlcv`의 최신 값을 추출(Enrichment)합니다.
- **전일 종가(`prev_close`) 추출 로직**: 단순히 `daily_ohlcv`의 최신 로우를 가져오는 것이 아니라, `d.date < (minute_ohlcv의 최신 date)` 조건을 추가하여 야간이나 주말(스케줄러가 이미 daily 테이블을 오늘 날짜로 덮어씌운 상황)에도 완벽하게 1영업일 이전의 종가를 가져오도록 강제합니다.

## Alternatives Considered
- **파이썬(Pandas) 메모리 조인**: OOM(Out of Memory) 발생 위험으로 기각.
- **프론트엔드 개별 API 호출**: 50개 종목의 실시간 데이터를 가져오기 위해 클라이언트가 50번의 API를 쏘면 KIS API Rate Limit(초당 20회)에 즉시 걸리므로 기각.
- **일반 LEFT JOIN**: 시계열 테이블에서 티커별 최신 1건만 가져오는 쿼리는 윈도우 함수(`ROW_NUMBER`)가 필요해 무거워짐. 반면 스칼라 서브쿼리(`ORDER BY date DESC LIMIT 1`)는 PK 인덱스를 직접 타므로 수집 건 조회 시 압도적으로 빠름.

## Consequences
- 1GB RAM 환경에서 부하 없이 수 밀리초(ms) 내에 풍부한 리치 데이터를 프론트엔드로 전달할 수 있습니다.
- 백엔드 쿼리에 의존하므로 프론트엔드는 데이터 포맷팅(억 단위, 등락률 계산 및 색상) 및 렌더링에만 집중할 수 있습니다.
- 향후 에이전트는 결과 집합을 확장할 때 무조건 '스칼라 서브쿼리' 패턴을 재사용해야 합니다.
