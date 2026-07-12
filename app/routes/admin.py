from fastapi import APIRouter
from services.admin_test_service import (
    test_daily_scheduler_integration_service,
    test_minute_scheduler_integration_service,
)

router = APIRouter()
test_router = APIRouter(prefix="/admin/test", tags=["Admin (Test)"])


@test_router.get("/daily_scheduler")
async def test_daily_scheduler_integration():
    """
    운영 DB를 보호하기 위해 test_trading.db를 임시 생성하고,
    무작위 3종목에 대해 [콜드스타트 -> 갭필(복구) -> 데이터 무결성 검증]을 수행합니다.
    """
    return await test_daily_scheduler_integration_service()


@test_router.get("/minute_scheduler")
async def test_minute_scheduler_integration():
    """
    운영 DB를 보호하기 위해 test_trading.db를 임시 생성하고,
    무작위 3종목에 대해 [분봉 콜드스타트 -> 갭필(복구) -> 데이터 무결성 검증]을 수행합니다.
    """
    return await test_minute_scheduler_integration_service()


router.include_router(test_router)
