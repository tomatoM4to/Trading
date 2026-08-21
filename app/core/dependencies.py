import os
import secrets
from typing import Annotated

from core.state import system_state
from fastapi import Header, HTTPException, Request, status


def verify_admin_api_key(
    x_admin_key: Annotated[str | None, Header(alias="X-Admin-Key")] = None,
) -> None:
    """Protect operational endpoints with a fail-closed shared secret."""
    configured_key = os.getenv("ADMIN_API_KEY")
    if not configured_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관리자 API가 구성되지 않았습니다.",
        )
    if x_admin_key is None or not secrets.compare_digest(x_admin_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 관리자 인증 정보입니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


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
