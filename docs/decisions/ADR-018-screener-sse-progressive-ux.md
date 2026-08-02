# ADR-018: Real-time Progressive UX via Server-Sent Events (SSE)

## Status
Accepted

## Date
2026-08-03

## Context
전략 스크리너 기능에서 다중 조건(이평선 정배열, 크로스 등)을 교집합/합집합으로 연산할 때, 데이터 양과 연산 복잡도에 따라 실행 시간이 1분 이상 소요될 수 있습니다. 
이로 인해 기존의 단일 JSON 반환 방식(`ScreenerResponse`)은 클라이언트/로드밸런서 단에서 HTTP Timeout이 발생할 위험이 높았고, 유저는 빈 로딩 화면만 쳐다봐야 하는 치명적인 UX 문제를 안고 있었습니다.

## Decision
- **FastAPI StreamingResponse 도입**: 복잡하고 무거운 비동기 큐(Celery, Redis) 아키텍처를 도입하여 1GB RAM 서버를 혹사시키는 대신, 단순히 HTTP 프로토콜의 표준인 SSE(Server-Sent Events)를 채택합니다.
- **POST 방식의 SSE**: 브라우저 기본 `EventSource`는 GET만 지원하므로, 프론트엔드에서는 `@microsoft/fetch-event-source` 라이브러리를 사용하여 POST Body(AST 필터 조건)를 전달하면서 스트림을 읽습니다.
- **Progressive Rendering**: 백엔드의 파이프라인(`ScreenerEngine`)은 각 필터를 통과할 때마다 `{"type": "progress", "filter_id": "...", "remaining": N}` 이벤트를 푸시합니다. 프론트엔드는 이를 받아 개별 필터 블록의 스피너를 체크마크(✅)로 순차 렌더링하고, 실시간으로 줄어드는 티커 개수를 표시합니다.

## Alternatives Considered
- **WebSockets**: 완전 양방향 통신이 필요 없으며(단순 백엔드 -> 프론트엔드 진행 상황 푸시), 세션 관리가 무거워 기각.
- **비동기 Job Queue + Polling**: 안정적이지만, 소규모 사이드 프로젝트에서 백그라운드 워커와 상태 저장용 캐시(Redis)를 세팅하는 것은 완벽한 오버엔지니어링(Over-engineering)이므로 기각.
- **단순 Chunked Streaming (빈 문자열 전송)**: 타임아웃은 방지할 수 있으나 유저에게 중간 진행 상황(어느 필터가 끝났는지)을 보여주지 못하므로 기각.

## Consequences
- 서버 자원을 추가로 소모하지 않고(파이썬 Set의 길이를 구하는 비용은 O(1)) 타임아웃을 완벽하게 방어했습니다.
- 유저에게 '기계가 내 지시를 단계별로 처리하고 있다'는 시각적 만족감(Wow factor)을 제공합니다.
- 프론트엔드 컴포넌트(`FilterBlock`)와 백엔드 통신 모듈(`fetchEventSource`)에 명확한 관심사 분리가 이루어졌습니다.
