from fastapi import APIRouter
from schemas.screener import ScreenerRequest, ScreenerResponse
from services.screener_service import screener_engine

router = APIRouter(prefix="/api/screener", tags=["Screener"])


@router.post("/run", response_model=ScreenerResponse)
async def run_screener(request: ScreenerRequest):
    """
    클라이언트가 정의한 필터 목록과 연산자(AND/OR)를 바탕으로 다이내믹 스크리닝을 수행합니다.
    """
    result_set = await screener_engine.run_pipeline(request)

    # Set을 이름이 포함된 리스트로 변환
    items = screener_engine.get_ticker_names(result_set)
    return ScreenerResponse(
        items=items,
        count=len(items)
    )
