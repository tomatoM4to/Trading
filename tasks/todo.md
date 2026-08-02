## Task 1: Backend SSE Streaming Logic Update

**Description:** `FilterNode` 스키마에 `id` 필드를 추가하고, `screener_service.py`에 SSE용 비동기 제너레이터 `run_pipeline_stream`을 추가합니다. 라우터는 이 제너레이터를 `StreamingResponse`로 감싸 반환합니다.

**Acceptance criteria:**
- [ ] `app/schemas/screener.py`의 `FilterNode` 클래스에 `id: str` 필드가 추가됨.
- [ ] `ScreenerEngine.run_pipeline_stream`이 작성되어, 필터마다 `{"type": "progress", "filter_id": "...", "remaining": N}`을 `yield`함.
- [ ] 연산 종료 시 `{"type": "complete", "items": [...]}`을 `yield`함.
- [ ] `app/routes/screener.py`의 엔드포인트가 `StreamingResponse(media_type="text/event-stream")`를 반환하도록 수정됨 (또는 기존 함수 교체).

**Verification:**
- [ ] `uv run fastapi dev app/main.py` 구동 후 오류 없음.

**Dependencies:** None

**Files likely touched:**
- `app/schemas/screener.py`
- `app/services/screener_service.py`
- `app/routes/screener.py`

**Estimated scope:** Medium: 3 files

---

## Task 2: Frontend POST Payload & Event-Source Integration

**Description:** 클라이언트가 백엔드로 `id`를 포함한 필터 페이로드를 보내고, 스트리밍 응답을 받아 파싱하는 통신 코드를 작성합니다.

**Acceptance criteria:**
- [ ] 패키지 의존성 추가: `npm i @microsoft/fetch-event-source` (또는 `pnpm`/`yarn` 등 해당 프로젝트 패키지 매니저에 맞게) 설치.
- [ ] `ScreenerBuilder.tsx`에서 POST 페이로드에 각 필터의 `id`를 포함함.
- [ ] 기존 `fetch()` 기반 백엔드 통신 코드를 `fetchEventSource()`로 교체함.
- [ ] `onmessage` 콜백을 통해 `progress` 및 `complete` 이벤트를 콘솔에 출력함.

**Verification:**
- [ ] 브라우저 네트워크 탭에서 EventStream 탭이 열리고 청크 단위로 데이터가 수신되는지 확인.

**Dependencies:** Task 1

**Files likely touched:**
- `web/package.json`
- `web/components/screener/ScreenerBuilder.tsx`

**Estimated scope:** Small: 2 files

---

## Task 3: Frontend UX/UI (Spinners and Counters)

**Description:** 스트리밍으로 전달되는 이벤트 데이터를 React 상태로 관리하고, 개별 필터 완료 표시 및 남은 티커 수(카운터)를 화면에 렌더링합니다.

**Acceptance criteria:**
- [ ] `ScreenerBuilder.tsx`에 `filterStatuses: Record<string, "pending" | "processing" | "done">` 상태가 추가됨.
- [ ] progress 이벤트를 받을 때마다 해당 `filter_id` 상태를 갱신하고 남은 티커 수를 UI에 표시함.
- [ ] 필터 블록 우측 또는 상단에 `Loader2`(lucide-react 스피너) 또는 `CheckCircle2` 아이콘을 그려 시각적 피드백 제공.
- [ ] `complete` 이벤트를 받으면 결과를 기존 테이블 컴포넌트에 넘기고 로딩 종료.

**Verification:**
- [ ] 스크리너 실행 시 필터들이 순차적으로 로딩 돌다가 완료 표기가 찍히는지 육안 확인.
- [ ] 최종 결과가 이전 버전과 동일하게 테이블에 출력되는지 확인.

**Dependencies:** Task 2

**Files likely touched:**
- `web/components/screener/ScreenerBuilder.tsx`
- (선택) `web/components/screener/FilterBlock.tsx`

**Estimated scope:** Medium: 2 files
