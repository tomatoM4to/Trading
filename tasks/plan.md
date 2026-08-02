# Implementation Plan: Screener Real-time Progress UX (via SSE)

## Overview
다중 필터 스크리너 연산 시 길어지는 대기 시간으로 인한 HTTP 타임아웃을 막고, 유저에게 현재 실행 중인 필터와 실시간으로 좁혀지는 종목 수를 시각적으로 피드백(Progressive Rendering)하기 위해 SSE(Server-Sent Events) 아키텍처를 도입합니다.

## Architecture Decisions
- **SSE with POST Payload**: 복잡한 필터 AST 페이로드를 전달해야 하므로 GET 방식의 브라우저 기본 `EventSource` 대신, `fetch` 기반의 스트림 리더 혹은 `@microsoft/fetch-event-source`를 사용하여 POST 방식으로 SSE를 수신합니다.
- **FastAPI StreamingResponse**: 별도의 비동기 큐(Celery/Redis) 없이 FastAPI 내장 `StreamingResponse`를 사용하여, 각 필터 연산이 완료될 때마다 즉시 `data: {...}\n\n` 형태의 이벤트를 푸시합니다.
- **Set Length for O(1) Progress**: 종목 교집합(`set`)의 크기(`len()`)를 구하는 비용은 O(1)이므로, 필터 연산 중간중간 남은 종목 수를 전달하여 서버 부하 없이 완벽한 점진적 피드백 UX를 완성합니다.

## Task List

### Phase 1: Backend SSE Streaming Foundation
- [ ] Task 1: 백엔드 스키마 및 SSE 스트리밍 로직 구현

### Checkpoint: Backend Complete
- [ ] curl 통신 테스트 시 `data: {"type": "progress", ...}` 청크(Chunk)가 순차적으로 밀려 들어오는가?
- [ ] 마지막에 `data: {"type": "complete", "items": [...]}`가 정상 반환되는가?

### Phase 2: Frontend SSE Consumer & UX
- [ ] Task 2: 프론트엔드 POST SSE 스트림 수신 로직 구현 (fetch-event-source 적용)
- [ ] Task 3: 프론트엔드 개별 필터 스피너/체크마크 UX 및 남은 종목 수 렌더링

### Checkpoint: Complete
- [ ] 스크리너 "실행" 버튼 클릭 시, 화면 상의 개별 필터 블록에 순차적으로 로딩(Spinner)과 완료(Check) 표시가 렌더링되는가?
- [ ] 중간 종목 수가 표시되고, 최종 테이블이 정상적으로 렌더링되는가?
- [ ] Ready for review

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| 프론트엔드 상태 업데이트 빈도 문제 | Med | 리렌더링 최적화를 위해 React 상태를 너무 잘게 쪼개지 않고, filterStatus 맵 하나로 통합 관리 |
| KIS API Rate Limit 또는 DB 락 | Low | 이미 파이프라인(Set 연산)과 스칼라 서브쿼리가 고도로 최적화되어 있으므로, 단순히 렌더링 과정(스트리밍)만 쪼개는 것은 백엔드 부하를 전혀 가중시키지 않음 |

## Open Questions
- 개별 필터의 완료 상태를 `FilterBlock` 안쪽에 아이콘으로 그릴지, 아니면 우측에 배지 형태로 그릴지 미세 조정 필요.
