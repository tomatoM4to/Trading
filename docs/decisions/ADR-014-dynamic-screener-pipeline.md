# ADR 014: Dynamic Screener Pipeline with Set-Theory & SQLite Push-down

## 1. Context (배경)
클라이언트(프론트엔드)에서 동적 파라미터(예: 특정 이평선 3일 연속 상승, 이격도 5% 이내 등)를 조합하여 실시간으로 2,400개 종목을 필터링하는 "다이내믹 스크리너 엔진"이 필요하다. 
현재 오라클 클라우드 서버는 1GB RAM의 제약을 가지고 있으며, KIS OpenAPI는 초당 20건의 Rate Limit이 존재한다. Pandas를 활용하여 2,400개 종목의 OHLCV를 병합(Merge)하고 메모리에서 필터링하는 방식은 OOM(Out of Memory)을 유발할 위험이 크다.

## 2. Decision (결정)
1. **Set-Theory Pipeline**: 모든 개별 필터 모듈(이평선, 이격도, 수급 등)은 조건을 만족하는 종목 코드의 집합(`Set[str]`)만을 반환하며, 중앙 오케스트레이터(`screener_service.py`)에서 순수 파이썬 내장 `Set` 교집합(`&`) 및 합집합(`|`) 연산만을 수행하여 최종 종목을 도출한다.
2. **Flat List Schema**: 복잡한 무한 뎁스 재귀 AST 대신, 프론트엔드는 1차원 필터 리스트(`filters`)와 필터 개수-1 크기의 연산자 리스트(`operations`)를 전송하는 직관적이고 평면적인 구조를 사용한다.
3. **SQLite Push-down**: 기술적 지표(이평선 연속 우상향 등) 연산은 파이썬으로 데이터를 끌어오지 않고, SQLite 내부의 Window Function(`LAG`, `ROW_NUMBER`, `AVG OVER`)과 CTE를 활용하여 단일 쿼리로 필터링을 완수(Push-down)한다. 분봉 추세와 일봉 추세를 모두 단일 패턴으로 지원한다.
4. **Late Evaluation (지연 평가)** / **Bulk API**: 외부 API(KIS 수급 데이터) 호출이 필요한 필터는 파이프라인의 후순위로 미루어 교집합을 통해 남은 소수의 종목만 찌르거나, 랭킹/집계 API를 활용하여 1회의 호출로 상위 100개 종목 `Set`을 가져오는 방식으로 Rate Limit을 회피한다.

## 3. Consequences (결과)
- **장점**: 1GB RAM 환경에서도 메모리 점유율을 거의 0에 가깝게 유지하며 OOM을 방지한다. KIS API 호출 속도 제한에 걸리지 않고 빠른 응답성을 보장한다.
- **단점**: 필터 모듈 추가 시, 파이썬 로직이 아닌 다소 복잡한 SQLite 윈도우 함수(CTE) 쿼리를 매번 정교하게 작성해야 하는 개발 복잡도가 증가한다.
