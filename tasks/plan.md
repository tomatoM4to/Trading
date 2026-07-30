# Implementation Plan: Backend Dynamic Screener Pipeline Engine

## Overview
클라이언트가 넘겨주는 JSON 형태의 트리(AST) 조건식을 파싱하여, 각 지표별로 종목 코드(Ticker)의 집합(Set)을 반환하게 한 뒤, 이들을 파이썬 메모리에서 빠른 교집합/합집합 연산(AND/OR)으로 묶어주는 Screener Pipeline Engine을 백엔드에 구축합니다. 
MVP 모델로서 첫 번째 구상된 필터인 "이평선 우상향 필터(MA Uptrend Filter)" 모듈을 함께 구현합니다.

## Architecture Decisions
- **Set-Theory 파이프라인**: 데이터를 무겁게 넘기지 않고 오직 `Set[str]` (티커 집합)만을 필터 모듈 간의 반환값으로 사용합니다.
- **단순화된 파이프라인 구조 (Flat List)**: 복잡한 재귀형 AST 대신, 단순히 여러 조건(Filter A, B, C)의 리스트를 받고, 이들을 한 번에 일괄 교집합(`AND`) 또는 합집합(`OR`) 처리하는 직관적이고 평면적인 Pydantic 모델을 사용합니다.
- **SQL Push-down (MA Uptrend)**: N일 동안 이평선의 기울기가 양수인지를 파이썬에서 계산하지 않고, SQLite의 Window 함수(`LAG` 등)를 이용해 쿼리단에서 조건을 만족하는 Ticker들만 뽑아내는 방식으로 메모리를 아낍니다.

## Task List

### Phase 1: Foundation (Schema & Engine Core)
- [ ] Task 1: `app/schemas/screener.py`를 생성하고 파이프라인 엔진을 위한 Pydantic 모델(플랫한 Filter 리스트와 Global Operator) 정의
- [ ] Task 2: `app/services/screener_service.py`를 생성하고, 리스트 내의 조건들을 순회하며 각 티커 집합을 구한 뒤 일괄 `&` (AND) 또는 `|` (OR) 연산을 수행하는 뼈대 작성

### Checkpoint: Foundation
- [ ] Pydantic 모델 검증 완비
- [ ] 엔진이 목업된 데이터(Mock Filters)에 대해 AND/OR 집합 연산을 정확히 수행하는지 확인

### Phase 2: Core Features (Uptrend Filter)
- [ ] Task 3: `screener_service.py` 내부에 `MAUptrendFilter` 로직 구현. SQLite를 사용해 N일 동안 선택된 다중 이평선(예: 20, 60선)의 값이 전일 대비 연속으로 상승한 종목 Ticker 리스트를 반환하는 쿼리 작성

### Phase 3: Route Integration
- [ ] Task 4: `app/routes/screener.py` 생성 및 `POST /api/screener/run` 엔드포인트 추가 (또는 기존 라우터에 병합). 클라이언트의 JSON 요청을 받아 파이프라인을 태우고 최종 Ticker 리스트를 반환

### Checkpoint: Complete
- [ ] 백엔드 서버 구동 후 cURL 또는 Swagger 문서에서 동적 필터(MA Uptrend + AND/OR 조합) 요청 시 정상 작동 확인

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| N일 연속 상승 쿼리의 성능 | High | SQLite 쿼리에서 N일 치 데이터를 전부 그룹화하여 점검하는 대신, Window Function(`LAG`)과 `SUM(CASE WHEN ...)` 기법으로 단일 스캔(Table Scan) 시 필터링되도록 최적화 |
