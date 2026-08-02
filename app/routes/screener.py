from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from schemas.screener import ScreenerRequest
from services.screener_service import screener_engine

router = APIRouter(prefix="/api/screener", tags=["Screener"])


@router.post("/run")
async def run_screener(request: ScreenerRequest):
    """
    프론트엔드에서 전달받은 조건(AST)을 기반으로 백엔드 파이프라인을 실행합니다 (SSE Stream).
    """
    try:
        return StreamingResponse(
            screener_engine.run_pipeline_stream(request),
            media_type="text/event-stream"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
