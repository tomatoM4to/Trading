from pydantic import BaseModel, Field


class TopVolumeItem(BaseModel):
    ticker: str = Field(..., description="단축코드")
    name: str = Field(..., description="종목명")
    volume: int = Field(..., description="누적 거래량")


class TopVolumeResponse(BaseModel):
    date: str = Field(..., description="영업일자")
    items: list[TopVolumeItem]


class ChartDataPoint(BaseModel):
    time: str = Field(..., description="타임스탬프 (분 단위, 예: 2026-07-24 09:00:00)")
    open: int
    high: int
    low: int
    close: int
    volume: int

    # 단기 이동평균선 (분봉 기준)
    ma1: float | None = None
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None

    # 장기 이동평균선 (일봉 기준 매핑)
    ma_daily_1: float | None = None
    ma_daily_5: float | None = None
    ma_daily_20: float | None = None
    ma_daily_60: float | None = None
    ma_daily_120: float | None = None


class ChartDataResponse(BaseModel):
    ticker: str
    name: str
    data: list[ChartDataPoint]
