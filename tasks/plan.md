# Implementation Plan: Foreign & Institutional Net Buy Rank Filters

## Overview
스크리너 엔진에 '외국인 순매수 상위(Top 30/60)' 및 '기관 순매수 상위(Top 30/60)' 종목을 추출하는 두 개의 개별 필터를 추가합니다. KIS OpenAPI 가집계 랭킹 API(`FHPTJ04400000`)를 활용하여 집합(Set) 형태로 반환하며, 기존 SQLite 기반의 기술적 필터들과 파이프라인에서 교집합(`&`) 연산이 가능하도록 구현합니다. 

## Architecture Decisions
- **Bulk Ranking Fetch**: 개별 종목마다 수급을 조회하지 않고, 랭킹 API 1~2회 호출로 상위 30~60개 종목을 통째로 가져와 Set-theory 연산에 활용합니다.
- **연속 조회(Pagination) 지원**: 사용자가 파라미터로 `limit` (예: 30 또는 60)을 지정할 수 있게 하여, 30 초과 시 `tr_cont="N"`을 이용해 2번째 페이지까지 연속 호출하는 로직을 내장합니다.
- **분리된 원자적 필터(Atomic Filter)**: 프론트엔드 UI의 조합 유연성을 극대화하기 위해 '외국인'과 '기관' 필터를 독립적인 타입(`foreign_net_buy_rank`, `inst_net_buy_rank`)으로 제공합니다.

## Task List

### Phase 1: Foundation
- [ ] Task 1: `ScreenerEngine` 내 KIS API 통신 및 페이징 헬퍼 함수(`_fetch_investor_rank`) 구현

### Checkpoint: Foundation
- [ ] KIS API 통신이 정상 작동하며, 30개 및 60개 요청 시 랭킹 데이터를 정확히 `Set[str]`으로 반환하는지 확인

### Phase 2: Core Features
- [ ] Task 2: `foreign_net_buy_rank`, `inst_net_buy_rank` 필터 핸들러 구현 및 라우팅 연결

### Checkpoint: Core Features
- [ ] 필터 파이프라인에 두 필터를 추가했을 때, 기존 필터들과 정상적으로 교집합 연산이 수행되는지 확인

### Phase 3: Documentation
- [ ] Task 3: `docs/screener.md` 파일에 신규 필터 스펙 및 파라미터(`limit`) 업데이트

### Checkpoint: Complete
- [ ] 모든 구현 완료 및 리뷰 준비

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| KIS API Rate Limit 초과 | High | 단건 조회가 아닌 Bulk 랭킹 API를 사용하고, 최대 연속 호출 횟수를 엄격히 제한(예: 60개로 캡)하여 API 호출 수를 최소화합니다. |
| API 응답 필드 변경 / 누락 | Med | 종목코드 추출 시 `mksc_shrn_iscd` 및 `stck_shrn_iscd`를 모두 확인하는 fallback 로직을 추가하여 호환성을 높입니다. |
