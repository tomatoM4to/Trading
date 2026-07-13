import sqlite3
from enum import StrEnum

from core.database import get_db
from fastapi import APIRouter, Depends
from services.admin_live_service import (
    get_global_status_service,
    get_ticker_status_service,
)
from services.admin_test_service import (
    test_daily_scheduler_integration_service,
    test_minute_scheduler_integration_service,
)

router = APIRouter()
test_router = APIRouter(prefix="/admin/test", tags=["Admin (Test)"])
live_router = APIRouter(prefix="/admin/live", tags=["Admin (Live Status)"])


class DataTypeEnum(StrEnum):
    daily = "daily"
    minute = "minute"


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


@live_router.get("/global-status")
def get_global_status(
    data_type: DataTypeEnum, conn: sqlite3.Connection = Depends(get_db)
):
    """
    전체 종목을 대상으로 지정한 데이터(일봉/분봉)의 최신 적재 상태를 확인합니다.
    """
    return get_global_status_service(data_type.value, conn)


@live_router.get("/ticker-status/{ticker}")
def get_ticker_status(
    ticker: str, data_type: DataTypeEnum, conn: sqlite3.Connection = Depends(get_db)
):
    """
    특정 종목의 지정한 데이터(일봉/분봉) 누적 개수와 날짜 범위를 조회합니다.
    """
    return get_ticker_status_service(ticker, data_type.value, conn)


router.include_router(test_router)
router.include_router(live_router)
