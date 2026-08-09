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


def get_minute_last_times(markets: list[str] | None = None) -> dict[str, str]:
    """
    DB에서 해당 시장 종목들의 가장 최근 분봉 시간(last_datetime)을 조회합니다.
    Returns: { "005930": "20260710153000", ... }
    """
    if not markets:
        markets = ["KOSPI", "KOSDAQ"]

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(markets))
        # 문자열 결합(||)으로 YYYYMMDDHHMMSS 생성 후 MAX
        cursor.execute(
            f"""
            SELECT d.ticker, MAX(CAST(d.date AS TEXT) || printf('%06d', d.time)) as last_datetime
            FROM minute_ohlcv d
            JOIN stock_codes s ON d.ticker = s.ticker
            WHERE s.market IN ({placeholders})
            GROUP BY d.ticker
            """,
            markets,
        )
        last_times = {row["ticker"]: row["last_datetime"] for row in cursor.fetchall()}
        return last_times
    except Exception as e:
        logger.error(f"Failed to fetch last times from DB: {e}")
        return {}
    finally:
        conn.close()


async def fetch_minute_data(
    ticker: str, target_date: str, target_time: str, priority: int = 7
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
        priority=priority,
    )

    if resp.is_ok():
        raw_list = resp.get_body().get("output2", [])
        if not raw_list:
            return pd.DataFrame()
        pure_list = [dict(row) for row in raw_list]
        return pd.DataFrame(pure_list)

    raise Exception(f"API Error: {resp.get_error_message()}")


async def process_ticker(
    ticker: str,
    last_datetime: str | None = None,
    limit_days: int = 14,
    max_steps: int = 15,
    priority: int = 7,
) -> tuple[bool, str | None]:
    """
    단일 종목의 분봉 데이터를 가져와 DB에 UPSERT합니다.
    last_datetime (YYYYMMDDHHMMSS) 가 주어지면, 해당 시간과 겹치는(Overlap) 부분을 감지하여
    루프를 즉시 종료(Early Exit)합니다.
    Returns: (성공여부, 이번 수집에서 확인한 가장 최신 분봉의 datetime 문자열)
    """
    now = datetime.now()
    target_date = now.strftime("%Y%m%d")
    target_time = now.strftime("%H%M00")
    cutoff_date = (now - timedelta(days=limit_days)).strftime("%Y%m%d")

    success_any = False
    newest_dt: str | None = None

    # 최대 max_steps 번 연속 조회
    for _ in range(max_steps):
        if target_date < cutoff_date:
            break

        df = await fetch_minute_data(
            ticker, target_date, target_time, priority=priority
        )
        if df.empty:
            # 엣지 케이스: 야간(예: 새벽 1시)이나 휴일 등 해당 일자에 데이터가 아예 없는 경우
            # 루프를 종료하지 않고 전날 장 마감 시간(15:30)으로 셋팅하여 계속 탐색
            try:
                curr_date = datetime.strptime(target_date, "%Y%m%d")
                prev_date = curr_date - timedelta(days=1)
                target_date = prev_date.strftime("%Y%m%d")
                target_time = "153000"
                continue
            except Exception as e:
                logger.error(f"Failed to calculate previous date for {ticker}: {e}")
                break

        # 'datetime' string column for easy comparison
        df["dt_str"] = df["stck_bsop_date"] + df["stck_cntg_hour"]

        if newest_dt is None:
            newest_dt = df["dt_str"].max()

        fetched_min_dt = df["dt_str"].min()
        fetched_len = len(df)

        # 중복 감지 조기 종료 (Overlap-Aware Early Exit)
        is_overlap = False
        if last_datetime:
            if fetched_min_dt <= last_datetime:
                is_overlap = True

            # DB에 이미 있는 시간대 이후의 새로운 데이터만 남김
            df = df[df["dt_str"] > last_datetime]
            if df.empty:
                # 필터링 후 남은 게 없으면 삽입할 필요 없이 바로 탈출
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

        # 거래대금 차분(diff) 계산
        if "acml_tr_pbmn" in df.columns:
            acml_amount = pd.to_numeric(df["acml_tr_pbmn"], errors="coerce")
            is_same_date = df["stck_bsop_date"] == df["stck_bsop_date"].shift(-1)
            diff_amount = acml_amount - acml_amount.shift(-1)
            df_clean["amount"] = diff_amount.where(is_same_date, acml_amount)

            is_last_row = df["stck_bsop_date"].shift(-1).isna()
            is_0900 = df["stck_cntg_hour"] == "090000"
            df_clean["amount"] = df_clean["amount"].mask(
                is_last_row & ~is_0900, df_clean["close"] * df_clean["volume"]
            )
        else:
            df_clean["amount"] = df_clean["close"] * df_clean["volume"]

        df_clean = df_clean.dropna(subset=["date", "time", "close"])
        if not df_clean.empty:
            success_any = True

            from core.database import connect_ma_db, connect_sqlite
            from core.ma_calculator import ma_calculator

            # 연산 시계열 보장을 위해 시간순(ASC) 정렬
            df_clean = df_clean.sort_values(by=["date", "time"], ascending=[True, True])

            records = df_clean.to_dict("records")
            ma_records = []

            for row in records:
                ma_calculator.add_minute_close(row["ticker"], row["close"])
                ma = ma_calculator.get_minute_ma(row["ticker"])
                ma_records.append(
                    {
                        "ticker": row["ticker"],
                        "date": row["date"],
                        "time": row["time"],
                        "ma5": ma["ma5"],
                        "ma10": ma["ma10"],
                        "ma20": ma["ma20"],
                        "ma60": ma["ma60"],
                        "ma120": ma["ma120"],
                        "ma200": ma["ma200"],
                    }
                )

            conn = connect_sqlite()
            ma_conn = connect_ma_db()
            try:
                # 1. OHLCV -> 디스크 DB
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

                # 2. MA -> 인메모리 DB
                ma_cursor = ma_conn.cursor()
                ma_insert_sql = """
                    INSERT OR REPLACE INTO minute_ma (
                        ticker, date, time, ma5, ma10, ma20, ma60, ma120, ma200
                    ) VALUES (
                        :ticker, :date, :time, :ma5, :ma10, :ma20, :ma60, :ma120, :ma200
                    )
                """
                ma_cursor.executemany(ma_insert_sql, ma_records)
                ma_conn.commit()
            except Exception as e:
                logger.error(f"[{ticker}] DB Insert Error: {e}")
            finally:
                conn.close()
                ma_conn.close()

        # 중복이 감지되었다면 과거 데이터를 더 뒤질 필요가 없으므로 즉시 탈출
        if is_overlap:
            break

        # 다음 과거 페이지 조회 설정
        # (주의: len(df)가 아니라 필터링 전 원본 길이인 fetched_len 기준)
        if fetched_len >= 100:
            target_date = fetched_min_dt[:8]
            target_time = fetched_min_dt[8:]
        else:
            try:
                curr_date = datetime.strptime(target_date, "%Y%m%d")
                prev_date = curr_date - timedelta(days=1)
                target_date = prev_date.strftime("%Y%m%d")
                target_time = "153000"
            except Exception as e:
                logger.error(f"Failed to calculate previous date for {ticker}: {e}")
                break

    return success_any, newest_dt


async def run_minute_ohlcv_scheduler(
    markets: list[str] | None = None,
    single_cycle: bool = False,
    priority: int = 7,
):
    if not markets:
        markets = ["KOSPI", "KOSDAQ"]

    market_str = ", ".join(markets)
    logger.sched(
        f"[SCHED] Starting Unified Minute OHLCV Scheduler for {market_str} (single_cycle={single_cycle})..."
    )

    # Gap Analysis (최초 1회만 DB에서 로드, 이후엔 메모리에서 업데이트)
    last_times = get_minute_last_times(markets)

    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(markets))
        cursor.execute(
            f"SELECT ticker FROM stock_codes WHERE market IN ({placeholders}) AND is_halted = 0",
            markets,
        )
        tickers = [row["ticker"] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return
    finally:
        conn.close()

    logger.sched(f"[SCHED] Found {len(tickers)} active tickers for {market_str}.")

    # 무한 루프 시작 (장 마감시 종료)
    while True:
        queue = asyncio.Queue()
        for ticker in tickers:
            queue.put_nowait({"ticker": ticker, "requeue_count": 0})

        success_count = 0
        fail_count = 0

        async def worker(w_queue: asyncio.Queue):
            nonlocal success_count, fail_count
            while True:
                try:
                    item = await w_queue.get()
                except asyncio.CancelledError:
                    break

                ticker = item["ticker"]
                requeue_count = item["requeue_count"]
                last_datetime = last_times.get(ticker)

                try:
                    # 단일 루프 (최대 15스텝이되, 중복 시 1스텝 만에 자동 탈출)
                    success, newest_dt = await process_ticker(
                        ticker, last_datetime, max_steps=15, priority=priority
                    )
                    if newest_dt:
                        last_times[ticker] = newest_dt  # 메모리 업데이트

                    success_count += 1
                    if (success_count + fail_count) % 500 == 0:
                        logger.sched(
                            f"[SCHED] {success_count + fail_count}/{len(tickers)} tickers processed in this cycle..."
                        )
                except Exception:
                    if requeue_count < 3:
                        item["requeue_count"] += 1
                        await asyncio.sleep(0.5)
                        await w_queue.put(item)
                    else:
                        fail_count += 1
                finally:
                    w_queue.task_done()

        workers = [asyncio.create_task(worker(queue)) for _ in range(50)]
        await queue.join()
        for w in workers:
            w.cancel()

        logger.sched(
            f"[SCHED] Cycle Finished. Success: {success_count}, Fail: {fail_count}."
        )

        if single_cycle:
            logger.info("Single cycle finished. Exiting minute scheduler (test mode).")
            break

        now_time = datetime.now().time()
        # 15:55 이후면 1사이클만 돌고(백필) 스케줄러 종료 (내일 08:55분에 다시 켜짐)
        if now_time >= datetime.strptime("15:55", "%H:%M").time():
            logger.sched(
                "[SCHED] Market is closed (15:55). Stopping Minute Scheduler until tomorrow."
            )
            break

        await asyncio.sleep(1)


_running_minute_scheduler_task: asyncio.Task | None = None


async def start_minute_scheduler_task(markets: list[str] | None = None):
    global _running_minute_scheduler_task
    if (
        _running_minute_scheduler_task is not None
        and not _running_minute_scheduler_task.done()
    ):
        return False

    loop = asyncio.get_running_loop()
    _running_minute_scheduler_task = loop.create_task(
        run_minute_ohlcv_scheduler(markets)
    )
    return True


def stop_minute_scheduler_task():
    global _running_minute_scheduler_task
    if (
        _running_minute_scheduler_task is not None
        and not _running_minute_scheduler_task.done()
    ):
        _running_minute_scheduler_task.cancel()
        return True
    return False
