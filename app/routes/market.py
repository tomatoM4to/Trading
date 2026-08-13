from datetime import datetime, timedelta

from core.kis_fetch import async_kis_fetch
from fastapi import APIRouter, HTTPException
from schemas.market import ChartDataResponse, TopVolumeResponse
from services.market_service import get_chart_data, get_top_volume_tickers

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/samsung/ohlcv")
async def get_samsung_ohlcv():
    """
    삼성전자(005930)의 최근 100일 일봉(OHLCV) 데이터를 조회합니다.
    """
    # KIS API 파라미터 준비
    api_url = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    tr_id = "FHKST03010100"  # 주식 일/주/월/년 차트 시세 TR_ID

    # 최근 100일 날짜 계산
    today = datetime.now()
    past = today - timedelta(days=100)

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식, ETF, ETN
        "FID_INPUT_ISCD": "005930",  # 종목코드 (삼성전자)
        "FID_INPUT_DATE_1": past.strftime("%Y%m%d"),  # 조회 시작일자
        "FID_INPUT_DATE_2": today.strftime("%Y%m%d"),  # 조회 종료일자
        "FID_PERIOD_DIV_CODE": "D",  # D: 일봉
        "FID_ORG_ADJ_PRC": "0",  # 0: 수정주가, 1: 원주가
    }

    # async_kis_fetch를 통해 Queue를 거쳐 안전하게 KIS 통신
    resp = await async_kis_fetch(
        api_url=api_url, ptr_id=tr_id, tr_cont="", params=params
    )

    if not resp.is_ok():
        raise HTTPException(
            status_code=400, detail=f"KIS API Error: {resp.get_error_message()}"
        )

    # 응답 본문에서 OHLCV 데이터 추출
    body = resp.get_body()

    # output2 배열에 실제 일별 시세 데이터가 담겨 있습니다.
    # DotDict를 사용했기 때문에 바로 리스트 내 딕셔너리로 접근 가능
    ohlcv_data = body.output2

    # 응답 데이터 정제 및 반환
    results = []
    for item in ohlcv_data:
        # 데이터가 비어있는 빈 행도 간혹 포함될 수 있으므로 체크
        if not item.stck_bsop_date:
            continue

        results.append(
            {
                "date": item.stck_bsop_date,  # 영업일자
                "open": item.stck_oprc,  # 시가
                "high": item.stck_hgpr,  # 고가
                "low": item.stck_lwpr,  # 저가
                "close": item.stck_clpr,  # 종가
                "volume": item.acml_vol,  # 누적 거래량
            }
        )

    return {
        "ticker": "005930",
        "name": "삼성전자",
        "period": "최근 100일",
        "data_count": len(results),
        "data": results,
    }


@router.get("/screener/top-volume", response_model=TopVolumeResponse)
async def get_top_volume():
    """
    최근 영업일 기준 거래대금/거래량 상위 30개 종목을 조회합니다.
    """
    return await get_top_volume_tickers(limit=30)


@router.get("/chart/{ticker}", response_model=ChartDataResponse)
async def get_chart(ticker: str, days: int = 3, type: str = "minute"):
    """
    특정 종목의 차트 데이터 및 다중 주기 이평선 데이터를 조회합니다.
    type: 'minute' (분봉) 또는 'daily' (일봉)
    """
    if type not in ("minute", "daily"):
        raise HTTPException(
            status_code=400, detail="유효하지 않은 type 입니다. ('minute' 또는 'daily')"
        )
    if days < 1 or days > 500:
        raise HTTPException(
            status_code=400, detail="조회 기간(days)은 1~500 범위여야 합니다."
        )

    return await get_chart_data(ticker, days=days, timeframe=type)
