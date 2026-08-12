# Implementation Plan: System State Guard

## 1. Components & Dependencies
- `app/core/state.py`: New module defining the thread-safe `SystemState` singleton.
- `app/core/dependencies.py`: New module defining the `system_state_guard` dependency.
- `app/main.py`: Inject the dependency globally into the FastAPI app.
- `app/core/scheduler.py` & `app/core/bootstrap.py`: Add `with system_state.acquire(...)` around heavy tasks.

## 2. Implementation Order
1. **State Module**: Create `app/core/state.py` with `is_available` flag and `acquire` context manager.
2. **Dependency**: Create `app/core/dependencies.py` which checks the state and raises `HTTPException(503, detail=reason)`. Bypass `/health`.
3. **App Integration**: Update `app/main.py` to pass `dependencies=[Depends(system_state_guard)]` into `FastAPI(...)`.
4. **Task Protection**: Wrap heavy operations in `app/core/scheduler.py` (GC, Sync) and `app/core/bootstrap.py` (Hydration, Cold Start) with the context manager.

## 3. Risks & Mitigations
- **Risk**: `/health` API is blocked causing load balancers to think the server is dead.
- **Mitigation**: Explicitly skip the check if `request.url.path == "/health"` inside the dependency.
- **Risk**: Deadlocks if an exception is raised inside a heavy task.
- **Mitigation**: `contextmanager` uses `finally` block to always release the lock and restore availability.

## 4. Verification
- `ruff check .`
- Start server, call `/health` (should work). 
- Manually trigger a locked state and verify API returns 503 with the reason message.
