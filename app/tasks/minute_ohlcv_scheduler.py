import asyncio
import logging
from datetime import datetime

import pandas as pd

from core.database import connect_sqlite
from core.kis_fetch import async_kis_fetch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_URL = "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
TR_ID = "FHKST03010230"

async def fetch_minute_data(ticker: str, target_date: str, target_time: str) -> pd.DataFrame:
    """
    KIS API를 통해 최대 120개의 1분봉 데이터를 가져옵니다.
    """
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": target_time,
        "FID_INPUT_DATE_1": target_date,
        "FID_PW_DATA_INCU_YN": "N",
        "FID_FAKE_TICK_INCU_YN": "N"
    }

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = await async_kis_fetch(API_URL, TR_ID, "", params)
            if resp.is_ok():
                raw_list = resp.get_body().get("output2", [])
                if not raw_list:
                    return pd.DataFrame()
                # DotDict 객체 배열을 pandas에 그대로 넣으면 numpy __array_struct__ 충돌이 발생하므로 순수 dict로 캐스팅
                pure_list = [dict(row) for row in raw_list]
                return pd.DataFrame(pure_list)
            else:
                logger.error(f"[{ticker}] API Error: {resp.get_error_message()}")
                return pd.DataFrame()
        except Exception as e:
            logger.warning(f"[{ticker}] Fetch Exception (Attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                logger.info(f"[{ticker}] Retrying in 1 second...")
                await asyncio.sleep(1)
            else:
                logger.error(f"[{ticker}] Max retries exceeded.")
    return pd.DataFrame()

async def process_ticker(ticker: str) -> bool:
    """
    단일 종목의 분봉 데이터를 가져와 DB에 UPSERT합니다.
    (최신 데이터부터 과거로 거슬러 올라가는 Top-Down 방식이며, 야간/주말을 건너뛰기 위해
     실제 존재하는 캔들의 시간을 다음 루프의 기준으로 삼습니다)
    """
    now = datetime.now()
    target_date = now.strftime("%Y%m%d")
    target_time = now.strftime("%H%M00")

    success_any = False

    # 3일치 분봉(390분 * 3 = 1170분)을 100분씩 점프하며 적재하려면 약 12번의 루프가 필요합니다.
    # 안전하게 15번 루프를 돌도록 설정합니다.
    for _ in range(15):
        df = await fetch_minute_data(ticker, target_date, target_time)
        if df.empty:
            break

        # DB 스키마에 맞게 컬럼 매핑
        df_clean = pd.DataFrame()
        df_clean['ticker'] = [ticker] * len(df)
        df_clean['date'] = df['stck_bsop_date']
        df_clean['time'] = df['stck_cntg_hour']
        df_clean['open'] = pd.to_numeric(df['stck_oprc'], errors='coerce')
        df_clean['high'] = pd.to_numeric(df['stck_hgpr'], errors='coerce')
        df_clean['low'] = pd.to_numeric(df['stck_lwpr'], errors='coerce')
        df_clean['close'] = pd.to_numeric(df['stck_prpr'], errors='coerce')
        df_clean['volume'] = pd.to_numeric(df['cntg_vol'], errors='coerce')

        # --- 거래대금(amount) 정밀 계산 로직 ---
        # KIS API는 분봉별 거래대금을 주지 않고 '당일 누적 거래대금(acml_tr_pbmn)'만 반환합니다.
        # 배열이 최신->과거(내림차순)이므로: (현재 인덱스의 누적대금) - (다음 인덱스의 누적대금) = 해당 분봉의 거래대금
        if 'acml_tr_pbmn' in df.columns:
            acml_amount = pd.to_numeric(df['acml_tr_pbmn'], errors='coerce')

            # [치명적 버그 방어]: 120개 캔들이 여러 날짜(Days)에 걸쳐있을 경우,
            # 아침 9시 00분의 누적대금(작음)에서 전날 15시 30분의 누적대금(매우 큼)을 빼버려서 거래대금이 마이너스(-)가 되는 현상 방지
            is_same_date = df['stck_bsop_date'] == df['stck_bsop_date'].shift(-1)

            # 날짜가 같을 때만 차분(diff)을 인정하고, 날짜가 바뀌는 경계(아침 9시)에서는 누적대금이 곧 해당 분의 거래대금이므로 acml_amount를 그대로 사용
            diff_amount = acml_amount - acml_amount.shift(-1)
            df_clean['amount'] = diff_amount.where(is_same_date, acml_amount)

            # 단, 청크의 가장 마지막 행은 shift(-1)이 NaN이라서 is_same_date가 False가 됨.
            # 이 때 acml_amount가 그대로 들어가면 거래대금이 비정상적으로 폭증하는 스파이크가 발생하므로, 마지막 행만 종가*거래량 근사치로 대체
            is_last_row = df['stck_bsop_date'].shift(-1).isna()
            df_clean['amount'] = df_clean['amount'].mask(is_last_row, df_clean['close'] * df_clean['volume'])
        else:
            # 만약 API 스펙 변경으로 누적거래대금이 안 들어온다면 전체를 근사치로 계산
            df_clean['amount'] = df_clean['close'] * df_clean['volume']

        # 결측치 필터링
        df_clean = df_clean.dropna(subset=['date', 'time', 'close'])
        if not df_clean.empty:
            success_any = True

            # DB 저장 (고속 UPSERT)
            conn = connect_sqlite()
            try:
                records = df_clean.to_dict('records')
                cursor = conn.cursor()

                insert_sql = '''
                    INSERT OR REPLACE INTO minute_ohlcv (
                        ticker, date, time, open, high, low, close, volume, amount
                    ) VALUES (
                        :ticker, :date, :time, :open, :high, :low, :close, :volume, :amount
                    )
                '''
                cursor.executemany(insert_sql, records)
                conn.commit()
            except Exception as e:
                logger.error(f"[{ticker}] DB Insert Error: {e}")
            finally:
                conn.close()

        # --- 다음 루프를 위한 타겟 시간 설정 (Top-Down 핵심 로직) ---
        # KIS API는 최신 캔들이 맨 위(index 0), 과거 캔들이 맨 아래(index -1)에 옵니다.
        # 120개 캔들 중 밑에서 20번째(index -20) 캔들의 날짜와 시간을 다음 타겟으로 삼으면,
        # 휴장일(밤, 주말, 공휴일)을 수학적 계산 없이 완벽하게 건너뛰면서 정확히 20분만 오버랩됩니다.
        if len(df) > 100:
            target_date = df.iloc[100]['stck_bsop_date']
            target_time = df.iloc[100]['stck_cntg_hour']
        else:
            # 가져온 캔들이 100개 이하이면 더 이상 거슬러 올라갈 과거 데이터(신규 상장 등)가 없다는 뜻입니다.
            break

    return success_any

async def run_minute_ohlcv_scheduler(market: str = "KOSPI"):
    start_time = datetime.now()
    logger.info(f"Starting Minute OHLCV Scheduler for {market}...")

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM stock_codes WHERE market = ?", (market,))
        tickers = [row['ticker'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return
    finally:
        conn.close()

    logger.info(f"Found {len(tickers)} tickers for {market}. Starting Minute fetches...")

    # OCI 1GB RAM 메모리 터짐(OOM) 방지를 위해 세마포어를 일봉(100)보다 보수적인 20으로 설정
    sem = asyncio.Semaphore(20)

    success_count = 0
    fail_count = 0

    async def sem_process(t):
        nonlocal success_count, fail_count
        async with sem:
            is_success = await process_ticker(t)
            if is_success:
                success_count += 1
            else:
                fail_count += 1

            total_processed = success_count + fail_count
            if total_processed % 100 == 0:
                logger.info(f"[Progress] Processed {total_processed} minute tickers so far...")

    tasks = [sem_process(t) for t in tickers]

    # 모든 태스크 병렬 수행
    await asyncio.gather(*tasks)

    elapsed_time = datetime.now() - start_time
    logger.info(f"=== Minute OHLCV Scheduler Finished for {market} ===")
    logger.info(f"Total Attempted: {len(tickers)}")
    logger.info(f"Total SUCCESS: {success_count}")
    logger.info(f"Total FAILED: {fail_count}")
    logger.info(f"Elapsed Time: {elapsed_time}")
    logger.info("=====================================================")

_running_minute_scheduler_task: asyncio.Task | None = None

async def start_minute_scheduler_task(market: str = "KOSPI"):
    global _running_minute_scheduler_task
    if _running_minute_scheduler_task is not None and not _running_minute_scheduler_task.done():
        logger.warning("Minute scheduler is already running. Ignoring request.")
        return False

    loop = asyncio.get_running_loop()
    _running_minute_scheduler_task = loop.create_task(run_minute_ohlcv_scheduler(market))
    logger.info("Minute scheduler task started manually via admin route.")
    return True

async def stop_minute_scheduler_task():
    global _running_minute_scheduler_task
    if _running_minute_scheduler_task is not None and not _running_minute_scheduler_task.done():
        _running_minute_scheduler_task.cancel()
        logger.info("Minute scheduler task manually cancelled.")
        return True
    return False
