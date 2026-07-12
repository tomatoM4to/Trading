from pydantic import BaseModel

# --- Daily Verify Models ---


class VerifySummary(BaseModel):
    tickers_sampled: int
    total_candles_checked: int
    total_mismatches: int
    total_missing_in_db: int
    accuracy_rate: float


class CandleData(BaseModel):
    open: int
    high: int
    low: int
    close: int
    vol: int
    amt: int


class MismatchSample(BaseModel):
    date: str
    api: CandleData
    db: CandleData


class VerifyDetail(BaseModel):
    ticker: str
    name: str
    target_end_date: str
    candles_checked: int
    matches: int
    mismatches: int
    missing_in_db: int
    missing_dates: list[str]
    status: str
    mismatch_sample: list[MismatchSample]


class DailyVerifyResponse(BaseModel):
    overall_status: str
    summary: VerifySummary
    details: list[VerifyDetail]
