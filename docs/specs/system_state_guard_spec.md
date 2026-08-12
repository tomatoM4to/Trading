# Spec: System State Guard (글로벌 싱글톤 상태 객체 기반 API 차단기)

## Objective
1 OCPU/1GB RAM이라는 척박한 환경에서, 서버가 무거운 백그라운드 작업(지능형 GC, 콜드스타트, 메모리 DB 디스크 동기화 등)을 수행하는 도중에 인입되는 유저 API 트래픽을 원천 차단합니다. 이를 통해 OOM(Out of Memory)이나 SQLite 파일 락을 방지하며, 클라이언트에게는 503(Service Unavailable) 상태 코드와 함께 명확한 차단 사유(번호 코드 포함)를 반환하여 쾌적한 UX와 서버 안정성을 동시에 확보합니다.

## Tech Stack
- Python 3.12+ / FastAPI
- Python `threading.Lock` 및 `@contextmanager` (Thread-safe 상태 관리)
- FastAPI 글로벌 의존성 주입 (Global Dependency)

## Commands
- **Lint**: `uv run ruff check . --fix`
- **Format**: `uv run ruff format .`
- **Dev**: `uv run fastapi dev app/main.py` 

## Project Structure
- `app/core/state.py` → `SystemState` 싱글톤 객체 및 인스턴스 생성 (중첩 작업 처리를 위한 `_acquire_count` 내장)
- `app/core/dependencies.py` → `check_system_state` FastAPI 의존성 함수 추가 (단, `/health`는 우회)
- `app/main.py` → `FastAPI(dependencies=[Depends(system_state_guard)])` 앱 전역 적용
- `app/core/scheduler.py` 및 `bootstrap.py` 등 → 무거운 작업 수행 시 `with system_state.acquire(...):` 적용

## Code Style
상태 잠금 및 해제 시 데드락이 발생하지 않도록 철저히 `contextmanager` 패턴을 강제합니다.

```python
# [app/core/state.py 예시]
import threading
from contextlib import contextmanager
from typing import Tuple

class SystemState:
    def __init__(self):
        self._lock = threading.Lock()
        self._is_available = True
        self._reason = ""
        self._acquire_count = 0

    @property
    def status(self) -> Tuple[bool, str]:
        with self._lock:
            return self._is_available, self._reason

    @contextmanager
    def acquire(self, reason: str):
        with self._lock:
            if self._acquire_count == 0:
                self._is_available = False
                self._reason = reason
            self._acquire_count += 1
        try:
            yield
        finally:
            with self._lock:
                self._acquire_count -= 1
                if self._acquire_count == 0:
                    self._is_available = True
                    self._reason = ""

system_state = SystemState()
```

```python
# [app/core/dependencies.py 예시]
from fastapi import HTTPException, status, Request
from core.state import system_state

async def system_state_guard(request: Request):
    if request.url.path == "/health":
        return

    is_avail, reason = system_state.status
    if not is_avail:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=reason
        )
```

## Testing Strategy
- 수동 라우터(`/admin/test`)에서 의도적으로 `with system_state.acquire("테스트 중"):` 블록을 열고 10초 대기하게 만든 뒤, 다른 터미널에서 메인 API 호출을 시도하여 503 에러와 JSON Body(`{"detail": "테스트 중"}`)가 즉시 반환되는지 검증합니다.
- 예외가 발생하거나, 여러 백그라운드 작업이 겹쳐서 구동(`_acquire_count` 누적)되어도 모든 락이 해제된 이후에야 정확히 `is_available = True`로 롤백되는지 검증합니다.

## Boundaries
- **Always do**: 상태 변경 작업(`is_available = False`)은 반드시 `with system_state.acquire(...)` 블록을 사용해 진입할 것.
- **Ask first**: 특정 API를 추가로 차단 대상에서 제외해야 하는 경우. (현재는 `/health`만 우회 중)
- **Never do**: 상태 객체의 변수(`self._is_available`)를 외부 모듈에서 직접 접근하여 수정하는 행위 금지.

## Success Criteria
1. 지능형 GC나 콜드스타트 같은 작업이 시작되면 API 호출 시 즉시 503 코드를 뱉어낸다 (Fail-fast).
2. 백그라운드 작업이 완료되거나 에러로 크래시가 나면 상태가 자동으로 해제되어 정상 API 서비스로 즉각 복귀한다.
3. 이 차단기능이 특정 라우터에만 국한되지 않고 전체 애플리케이션(`app/main.py`)에 안전하게 의존성 주입된다.

## Open Questions (해결 완료)
- 인터뷰를 통해 1) `/health` 라우터는 우회시키고 `/admin`은 잠글 것, 2) 503 HTTP 상태 코드가 있으니 별도의 커스텀 code는 배제하고 `detail`에 사유(문자열)만 반환할 것으로 결정 및 스펙 반영 완료.
