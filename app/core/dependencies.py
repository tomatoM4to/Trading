from core.state import system_state
from fastapi import HTTPException, Request, status


async def system_state_guard(request: Request):
    """글로벌 시스템 상태 차단기 (FastAPI Dependency).
    시스템이 락(Lock)에 걸려있으면 즉시 503 상태 코드를 반환한다.
    /health 라우터는 제외된다.
    """
    if request.url.path == "/health":
        return

    is_avail, reason = system_state.status
    if not is_avail:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=reason,
        )
