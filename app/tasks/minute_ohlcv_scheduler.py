import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
from core.database import connect_sqlite
from core.kis_fetch import async_kis_fetch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_URL = "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
TR_ID = "FHKST03010230"


async def fetch_minute_data(
    ticker: str, target_date: str, target_time: str
) -> pd.DataFrame:
    """
    KIS API를 통해 최대 120개의 1분봉 데이터를 가져옵니다.
    """
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": target_time,
        "FID_INPUT_DATE_1": target_date,
        "FID_PW_DATA_INCU_YN": "N",
        "FID_FAKE_TICK_INCU_YN": "N",
    }

    resp = await async_kis_fetch(
        api_url=API_URL,
        ptr_id=TR_ID,
        tr_cont="",
        params=params,
        priority=7,  # 스케줄러 태스크는 실시간 요청보다 약간 낮은 우선순위 할당
    )

    if resp.is_ok():
        raw_list = resp.get_body().get("output2", [])
        if not raw_list:
            return pd.DataFrame()
        # DotDict 객체 배열을 pandas에 그대로 넣으면 numpy __array_struct__ 충돌이 발생하므로 순수 dict로 캐스팅
        pure_list = [dict(row) for row in raw_list]
        return pd.DataFrame(pure_list)

    raise Exception(f"API Error: {resp.get_error_message()}")


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
        df_clean["ticker"] = [ticker] * len(df)
        df_clean["date"] = df["stck_bsop_date"]
        df_clean["time"] = df["stck_cntg_hour"]
        df_clean["open"] = pd.to_numeric(df["stck_oprc"], errors="coerce")
        df_clean["high"] = pd.to_numeric(df["stck_hgpr"], errors="coerce")
        df_clean["low"] = pd.to_numeric(df["stck_lwpr"], errors="coerce")
        df_clean["close"] = pd.to_numeric(df["stck_prpr"], errors="coerce")
        df_clean["volume"] = pd.to_numeric(df["cntg_vol"], errors="coerce")

        # --- 거래대금(amount) 정밀 계산 로직 ---
        # KIS API는 분봉별 거래대금을 주지 않고 '당일 누적 거래대금(acml_tr_pbmn)'만 반환합니다.
        # 배열이 최신->과거(내림차순)이므로: (현재 인덱스의 누적대금) - (다음 인덱스의 누적대금) = 해당 분봉의 거래대금
        if "acml_tr_pbmn" in df.columns:
            acml_amount = pd.to_numeric(df["acml_tr_pbmn"], errors="coerce")

            # [치명적 버그 방어]: 120개 캔들이 여러 날짜(Days)에 걸쳐있을 경우,
            # 아침 9시 00분의 누적대금(작음)에서 전날 15시 30분의 누적대금(매우 큼)을 빼버려서 거래대금이 마이너스(-)가 되는 현상 방지
            is_same_date = df["stck_bsop_date"] == df["stck_bsop_date"].shift(-1)

            # 날짜가 같을 때만 차분(diff)을 인정하고, 날짜가 바뀌는 경계(아침 9시)에서는 누적대금이 곧 해당 분의 거래대금이므로 acml_amount를 그대로 사용
            diff_amount = acml_amount - acml_amount.shift(-1)
            df_clean["amount"] = diff_amount.where(is_same_date, acml_amount)

            # 단, 청크의 가장 마지막 행은 shift(-1)이 NaN이라서 is_same_date가 False가 됨.
            # 이 때 acml_amount가 그대로 들어가면 거래대금이 비정상적으로 폭증하는 스파이크가 발생하므로, 마지막 행만 종가*거래량 근사치로 대체
            # 단, 그 마지막 행이 09:00:00 이라면 누적대금이 곧 해당 분의 정확한 거래대금이므로 대체하지 않음.
            is_last_row = df["stck_bsop_date"].shift(-1).isna()
            is_0900 = df["stck_cntg_hour"] == "090000"
            df_clean["amount"] = df_clean["amount"].mask(
                is_last_row & ~is_0900, df_clean["close"] * df_clean["volume"]
            )
        else:
            # 만약 API 스펙 변경으로 누적거래대금이 안 들어온다면 전체를 근사치로 계산
            df_clean["amount"] = df_clean["close"] * df_clean["volume"]

        # 결측치 필터링
        df_clean = df_clean.dropna(subset=["date", "time", "close"])
        if not df_clean.empty:
            success_any = True

            # DB 저장 (고속 UPSERT)
            conn = connect_sqlite()
            try:
                records = df_clean.to_dict("records")
                cursor = conn.cursor()

                insert_sql = """
                    INSERT OR REPLACE INTO minute_ohlcv (
                        ticker, date, time, open, high, low, close, volume, amount
                    ) VALUES (
                        :ticker, :date, :time, :open, :high, :low, :close, :volume, :amount
                    )
                """
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
            target_date = df.iloc[100]["stck_bsop_date"]
            target_time = df.iloc[100]["stck_cntg_hour"]
        else:
            # 가져온 캔들이 100개 이하이면 해당 일자의 09:00:00(장 시작)에 도달했다는 뜻입니다.
            # KIS API는 주말이나 휴장일 날짜를 입력받아도 자동으로 그 직전 영업일 데이터를 반환하는
            # 훌륭한 특성이 있으므로, 복잡한 달력 계산 없이 단순히 날짜를 하루(-1일) 빼서 넘기면 됩니다.
            try:
                curr_date = datetime.strptime(target_date, "%Y%m%d")
                prev_date = curr_date - timedelta(days=1)
                target_date = prev_date.strftime("%Y%m%d")
                target_time = "153000"
            except Exception as e:
                logger.error(f"Failed to calculate previous date for {ticker}: {e}")
                break

    return success_any


async def run_minute_ohlcv_scheduler(market: str = "KOSPI"):
    start_time = datetime.now()
    logger.info(f"Starting Minute OHLCV Scheduler for {market}...")

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM stock_codes WHERE market = ?", (market,))
        tickers = [row["ticker"] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return
    finally:
        conn.close()

    logger.info(
        f"Found {len(tickers)} tickers for {market}. Starting Minute fetches..."
    )

    # 큐 기반 비동기 워커 생성
    queue = asyncio.Queue()
    for ticker in tickers:
        queue.put_nowait({"ticker": ticker, "requeue_count": 0})

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
            requeue_count = item["requeue_count"]

            try:
                await process_ticker(ticker)
                # 에러 없이 완료되었다면 성공으로 간주 (데이터 없는 신규상장 포함)
                success_count += 1

                total_processed = success_count + fail_count
                if total_processed % 100 == 0:
                    logger.info(
                        f"[Progress] Processed {total_processed} minute tickers so far..."
                    )
            except Exception as e:
                if requeue_count < 5:
                    item["requeue_count"] += 1
                    await asyncio.sleep(0.5)  # 실패 시 0.5초 대기 후 재진입 (백오프)
                    await queue.put(item)
                else:
                    logger.error(f"[{ticker}] Completely failed after 5 requeues: {e}")
                    fail_count += 1
            finally:
                queue.task_done()

    # 분봉은 일봉보다 메모리를 조금 더 쓰므로 워커 수를 50개로 안전하게 타협 설정
    num_workers = 50
    workers = [asyncio.create_task(worker()) for _ in range(num_workers)]

    # 모든 큐 작업이 끝날 때까지 대기
    await queue.join()

    # 대기 중인 워커 종료
    for w in workers:
        w.cancel()

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
    if (
        _running_minute_scheduler_task is not None
        and not _running_minute_scheduler_task.done()
    ):
        logger.warning("Minute scheduler is already running. Ignoring request.")
        return False

    loop = asyncio.get_running_loop()
    _running_minute_scheduler_task = loop.create_task(
        run_minute_ohlcv_scheduler(market)
    )
    logger.info("Minute scheduler task started manually via admin route.")
    return True


def stop_minute_scheduler_task():
    global _running_minute_scheduler_task
    if (
        _running_minute_scheduler_task is not None
        and not _running_minute_scheduler_task.done()
    ):
        _running_minute_scheduler_task.cancel()
        logger.info("Minute scheduler task manually cancelled.")
        return True
    return False
