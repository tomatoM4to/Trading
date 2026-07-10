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


async def fetch_and_save_ohlcv(
    ticker: str, end_date: datetime, days_to_subtract: int
) -> list[dict]:
    """특정 종목의 OHLCV 데이터를 KIS API로 조회하여 리스트로 반환"""
    start_date = end_date - timedelta(days=days_to_subtract)

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",  # J: 주식, ETF, ETN
        "FID_INPUT_ISCD": ticker,  # 종목코드
        "FID_INPUT_DATE_1": start_date.strftime("%Y%m%d"),  # 조회 시작일자
        "FID_INPUT_DATE_2": end_date.strftime("%Y%m%d"),  # 조회 종료일자
        "FID_PERIOD_DIV_CODE": "D",  # D: 일봉
        "FID_ORG_ADJ_PRC": "0",  # 0: 수정주가
    }

    resp = await async_kis_fetch(
        api_url=API_URL,
        ptr_id=TR_ID,
        tr_cont="",
        params=params,
        priority=7,  # 스케줄러 태스크는 실시간 요청보다 약간 낮은 우선순위 할당
    )

    if resp.is_ok():
        return resp.get_body().output2

    raise Exception(f"API Error: {resp.get_error_message()}")


async def process_ticker(
    ticker: str, last_date: str | None = None, target_api_calls: int = 5
):
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

        # [스마트 스케줄러] 우리가 가진 DB의 최신 날짜(last_date)와 겹치는 구간(이하)이 확보되면 즉시 과거 역추적 중단
        if last_date and oldest_date_str <= last_date:
            break

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
        processed_data.append(
            {
                "ticker": ticker,
                "date": item.stck_bsop_date,
                "open": int(item.stck_oprc),
                "high": int(item.stck_hgpr),
                "low": int(item.stck_lwpr),
                "close": int(item.stck_clpr),
                "volume": int(item.acml_vol),
                "amount": int(item.acml_tr_pbmn),
            }
        )

    if not processed_data:
        logger.info(f"[{ticker}] No valid OHLCV data found. Skipping.")
        return True

    # SQLite에 Bulk UPSERT (INSERT OR REPLACE)
    conn = connect_sqlite()
    try:
        df = pd.DataFrame(processed_data)
        # 중복 제거 (혹시 겹치는 날짜가 있을 경우)
        df.drop_duplicates(subset=["ticker", "date"], inplace=True)

        cursor = conn.cursor()
        cursor.executemany(
            """
            INSERT OR REPLACE INTO daily_ohlcv (ticker, date, open, high, low, close, volume, amount)
            VALUES (:ticker, :date, :open, :high, :low, :close, :volume, :amount)
        """,
            df.to_dict("records"),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[{ticker}] DB Save Error: {e}")
        raise e
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
        # 1. 시장에 해당하는 종목 코드 조회
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM stock_codes WHERE market = ?", (market,))
        tickers = [row["ticker"] for row in cursor.fetchall()]

        # 2. 각 종목별 최신 날짜(MAX date) 일괄 조회 (병목 방지용 메모리 매핑)
        cursor.execute(
            """
            SELECT d.ticker, MAX(d.date) as last_date
            FROM daily_ohlcv d
            JOIN stock_codes s ON d.ticker = s.ticker
            WHERE s.market = ?
            GROUP BY d.ticker
        """,
            (market,),
        )
        last_dates = {row["ticker"]: row["last_date"] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Failed to fetch tickers from DB: {e}")
        return
    finally:
        conn.close()

    logger.info(f"Found {len(tickers)} tickers for {market}. Starting fetches...")

    # 큐 기반 비동기 워커 생성
    queue = asyncio.Queue()
    for ticker in tickers:
        queue.put_nowait(
            {"ticker": ticker, "last_date": last_dates.get(ticker), "requeue_count": 0}
        )

    success_count = 0
    fail_count = 0

    async def worker():
        nonlocal success_count, fail_count
        while True:
            try:
                item = await queue.get()
            except asyncio.CancelledError:
                break

            ticker = item["ticker"]
            last_date = item["last_date"]
            requeue_count = item["requeue_count"]

            try:
                await process_ticker(ticker, last_date)
                success_count += 1
                if success_count % 100 == 0:
                    logger.info(
                        f"[Progress] Successfully saved {success_count} tickers so far..."
                    )
            except Exception as e:
                if requeue_count < 5:
                    # logger.warning(f"[{ticker}] Fetch failed ({e}). Requeueing ({requeue_count + 1}/5)...")
                    item["requeue_count"] += 1
                    await asyncio.sleep(0.5)  # 실패 시 0.5초 강제 대기 후 재진입
                    await queue.put(item)
                else:
                    logger.error(f"[{ticker}] Completely failed after 5 requeues: {e}")
                    fail_count += 1
            finally:
                queue.task_done()

    # 100개의 워커가 큐를 소비
    num_workers = 100
    workers = [asyncio.create_task(worker()) for _ in range(num_workers)]

    # 모든 작업이 끝날 때까지 대기
    await queue.join()

    # 작업 완료 후 워커 종료
    for w in workers:
        w.cancel()

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
