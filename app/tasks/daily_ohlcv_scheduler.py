import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd

from core.database import connect_sqlite
from core.kis_fetch import async_kis_fetch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
TR_ID = "FHKST03010100"  # 국내주식기간별시세

async def fetch_and_save_ohlcv(ticker: str, end_date: datetime, days_to_subtract: int, max_retries: int = 3) -> list[dict]:
    """특정 종목의 OHLCV 데이터를 KIS API로 조회하여 리스트로 반환 (재시도 로직 포함)"""
    start_date = end_date - timedelta(days=days_to_subtract)

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",       # J: 주식, ETF, ETN
        "FID_INPUT_ISCD": ticker,            # 종목코드
        "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),  # 조회 시작일자
        "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),    # 조회 종료일자
        "FID_PERIOD_DIV_CODE": "D",          # D: 일봉
        "FID_ORG_ADJ_PRC": "0"               # 0: 수정주가
    }

    for attempt in range(max_retries):
        try:
            resp = await async_kis_fetch(
                api_url=API_URL,
                ptr_id=TR_ID,
                tr_cont="",
                params=params,
                priority=7  # 스케줄러 태스크는 실시간 요청보다 약간 낮은 우선순위 할당
            )

            if resp.is_ok():
                if attempt > 0:
                    logger.info(f"[{ticker}] Fetch succeeded on retry {attempt+1}/{max_retries}!")
                return resp.get_body().output2

            logger.warning(f"[{ticker}] API Error (Attempt {attempt+1}/{max_retries}): {resp.get_error_message()}")
        except Exception as e:
            logger.warning(f"[{ticker}] Fetch Exception (Attempt {attempt+1}/{max_retries}): {e}")

        if attempt < max_retries - 1:
            logger.info(f"[{ticker}] Retrying in 1 second...")
            await asyncio.sleep(1)  # 1초 대기 후 재시도

    logger.error(f"[{ticker}] Completely failed to fetch OHLCV after {max_retries} attempts.")
    return []

async def process_ticker(ticker: str, target_api_calls: int = 5):
    """
    한 종목에 대해 여러 번 API를 호출하여 충분한 과거 데이터(예: 5번 호출 시 최대 500영업일)를 수집.
    200일 이평선을 과거 시점에서도 계산하려면 최소 400~500 영업일 치의 데이터가 필요함.
    """
    all_data = []

    # KIS API는 1회 호출에 최대 100건(영업일)을 반환하므로,
    # 응답으로 온 가장 오래된 날짜의 하루 전을 다음 호출의 종료일로 설정하여 거슬러 올라감.
    current_end_date = datetime.now()

    for _ in range(target_api_calls):
        # 주말/연휴/긴 거래정지 등을 고려하여 한 번에 200 캘린더 일수만큼 넉넉하게 요청
        # KIS API는 해당 기간 내 영업일 기준으로 최근 100건을 최대치로 반환함.
        chunk = await fetch_and_save_ohlcv(ticker, current_end_date, 200)

        valid_items = [item for item in chunk if item.stck_bsop_date]

        # 만약 200일이라는 긴 기간 동안 단 하나의 거래일도 없다면(상장 전이거나 장기 거래정지)
        # 루프를 종료하거나 다음 루프로 넘어감
        if not valid_items:
            break

        all_data.extend(valid_items)

        # 가져온 데이터 중 가장 과거 날짜를 찾아서 다음 루프의 end_date로 세팅
        oldest_date_str = min(item.stck_bsop_date for item in valid_items)
        oldest_date = datetime.strptime(oldest_date_str, "%Y%m%d")
        current_end_date = oldest_date - timedelta(days=1)

        # 상장한 지 얼마 안 된 종목이라 더 이상 과거 데이터가 안 나오면 중단
        if len(valid_items) < 10:
            break

    if not all_data:
        return

    # 데이터 정리
    processed_data = []
    for item in all_data:
        processed_data.append({
            "ticker": ticker,
            "date": item.stck_bsop_date,
            "open": int(item.stck_oprc),
            "high": int(item.stck_hgpr),
            "low": int(item.stck_lwpr),
            "close": int(item.stck_clpr),
            "volume": int(item.acml_vol)
        })

    if not processed_data:
        logger.warning(f"[{ticker}] No valid OHLCV data found. Skipping.")
        return False

    # SQLite에 Bulk UPSERT (INSERT OR REPLACE)
    conn = connect_sqlite()
    try:
        df = pd.DataFrame(processed_data)
        # 중복 제거 (혹시 겹치는 날짜가 있을 경우)
        df.drop_duplicates(subset=['ticker', 'date'], inplace=True)

        cursor = conn.cursor()
        cursor.executemany('''
            INSERT OR REPLACE INTO daily_ohlcv (ticker, date, open, high, low, close, volume)
            VALUES (:ticker, :date, :open, :high, :low, :close, :volume)
        ''', df.to_dict('records'))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[{ticker}] DB Save Error: {e}")
        return False
    finally:
        conn.close()

async def run_daily_ohlcv_scheduler(market: str = "KOSPI"):
    """
    지정된 시장의 모든 종목의 일봉 데이터를 수집하는 스케줄러.
    """
    start_time = datetime.now()
    logger.info(f"Starting Daily OHLCV Scheduler for {market}...")

    conn = connect_sqlite()
    try:
        # 시장에 해당하는 종목 코드 조회
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM stock_codes WHERE market = ?", (market,))
        tickers = [row['ticker'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch tickers from DB: {e}")
        return
    finally:
        conn.close()

    logger.info(f"Found {len(tickers)} tickers for {market}. Starting fetches...")

    # 병렬 처리를 너무 많이 하면 메모리나 다른 작업에 영향을 줄 수 있으므로 세마포어로 동시성 제어
    # (Rate Limit 자체는 kis_fetch 큐에서 20req/s로 방어해 주므로 걱정 없음)
    sem = asyncio.Semaphore(100)

    success_count = 0
    fail_count = 0

    async def sem_process(ticker):
        nonlocal success_count, fail_count
        async with sem:
            is_success = await process_ticker(ticker)
            if is_success:
                success_count += 1
                if success_count % 100 == 0:
                    logger.info(f"[Progress] Successfully saved {success_count} tickers so far...")
            else:
                fail_count += 1

    tasks = [sem_process(ticker) for ticker in tickers]

    # gather_with_concurrency (모든 태스크 동시 실행)
    await asyncio.gather(*tasks)

    elapsed_time = datetime.now() - start_time

    logger.info(f"=== Daily OHLCV Scheduler Finished for {market} ===")
    logger.info(f"Total Attempted: {len(tickers)}")
    logger.info(f"Total SUCCESS: {success_count}")
    logger.info(f"Total FAILED: {fail_count}")
    logger.info(f"Elapsed Time: {elapsed_time}")
    logger.info("=====================================================")

_running_scheduler_task: asyncio.Task | None = None

async def start_scheduler_task(market: str = "KOSPI"):
    """임시 라우터에서 백그라운드 태스크로 스케줄러를 구동할 때 사용"""
    global _running_scheduler_task
    if _running_scheduler_task is not None and not _running_scheduler_task.done():
        logger.warning("Scheduler is already running. Ignoring start request.")
        return False

    loop = asyncio.get_running_loop()
    _running_scheduler_task = loop.create_task(run_daily_ohlcv_scheduler(market))
    logger.info("Scheduler task started manually via admin route.")
    return True

def stop_scheduler_task():
    """임시 라우터에서 구동 중인 스케줄러를 강제 취소"""
    global _running_scheduler_task
    if _running_scheduler_task is not None and not _running_scheduler_task.done():
        _running_scheduler_task.cancel()
        logger.info("Scheduler task cancelled manually via admin route.")
        return True
    return False
