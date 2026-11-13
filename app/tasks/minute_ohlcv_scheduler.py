import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
from core.database import MINUTE_MA_RETENTION, connect_ma_db, connect_sqlite
from core.kis_fetch import async_kis_fetch
from core.ma_calculator import MACalculator
from core.state import system_state

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_URL = "/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice"
TR_ID = "FHKST03010230"


def normalize_minute_page(ticker: str, frame: pd.DataFrame) -> list[dict]:
    fields = {
        "date": "stck_bsop_date",
        "time": "stck_cntg_hour",
        "open": "stck_oprc",
        "high": "stck_hgpr",
        "low": "stck_lwpr",
        "close": "stck_prpr",
        "volume": "cntg_vol",
    }
    ordered = frame.sort_values(["stck_bsop_date", "stck_cntg_hour"])
    records = []
    seen = {}
    previous_date, previous_amount = None, None
    for item in ordered.to_dict("records"):
        row = {key: int(str(item[source])) for key, source in fields.items()}
        timestamp = f"{row['date']:08d}{row['time']:06d}"
        datetime.strptime(timestamp, "%Y%m%d%H%M%S")
        cumulative = item.get("acml_tr_pbmn")
        cumulative = int(str(cumulative)) if cumulative is not None else None
        normalized = (row, cumulative)
        if timestamp in seen:
            if seen[timestamp] != normalized:
                raise ValueError("Conflicting duplicate minute candle")
            continue
        seen[timestamp] = normalized
        amount = None
        if cumulative is not None:
            if previous_date == row["date"] and previous_amount is not None:
                amount = cumulative - previous_amount
            elif row["time"] == 90000:
                amount = cumulative
            if cumulative < 0 or (amount is not None and amount < 0):
                raise ValueError("Invalid cumulative minute amount")
        records.append(
            {
                "ticker": ticker,
                **row,
                "amount": amount,
                "cumulative_amount": cumulative,
                "dt_str": timestamp,
            }
        )
        previous_date, previous_amount = row["date"], cumulative
    return records


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


def rebuild_minute_ma_for_ticker(main_conn, ma_conn, ticker: str) -> None:
    """Rebuild one ticker's retained minute MA from canonical OHLCV order."""
    calculator = MACalculator()
    source_limit = MINUTE_MA_RETENTION + calculator.max_period - 1
    rows = main_conn.execute(
        """
        SELECT ticker, date, time, close
        FROM (
            SELECT ticker, date, time, close
            FROM minute_ohlcv
            WHERE ticker = ?
            ORDER BY date DESC, time DESC
            LIMIT ?
        )
        ORDER BY date, time
        """,
        (ticker, source_limit),
    ).fetchall()

    ma_records = []
    for row in rows:
        _, date, time, close = row
        calculator.add_minute_close(ticker, close)
        ma = calculator.get_minute_ma(ticker)
        ma_records.append(
            (
                ticker,
                date,
                time,
                ma["ma5"],
                ma["ma10"],
                ma["ma20"],
                ma["ma60"],
                ma["ma120"],
                ma["ma200"],
            )
        )

    ma_conn.execute("DELETE FROM minute_ma WHERE ticker = ?", (ticker,))
    ma_conn.executemany(
        "INSERT INTO minute_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ma_records[-MINUTE_MA_RETENTION:],
    )
    ma_conn.commit()


async def process_ticker(
    ticker: str,
    last_datetime: str | None = None,
    limit_days: int = 14,
    max_steps: int = 7,
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

    try:
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

            try:
                records = normalize_minute_page(ticker, df)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"[{ticker}] Invalid minute OHLCV response") from exc

            if newest_dt is None:
                newest_dt = records[-1]["dt_str"]

            fetched_min_dt = records[0]["dt_str"]
            fetched_len = len(df)

            # 중복 감지 조기 종료 (Overlap-Aware Early Exit)
            is_overlap = False
            if last_datetime:
                if fetched_min_dt <= last_datetime:
                    is_overlap = True

                records = [row for row in records if row["dt_str"] >= last_datetime]
                if not records:
                    break

            if records:
                conn = connect_sqlite()
                try:
                    cursor = conn.cursor()
                    last = records[-1]
                    previous = cursor.execute(
                        "SELECT cumulative_amount FROM minute_ohlcv WHERE ticker=? AND date=? AND time=?",
                        (ticker, last["date"], last["time"]),
                    ).fetchone()
                    insert_sql = """
                        INSERT INTO minute_ohlcv (
                            ticker, date, time, open, high, low, close, volume, amount, cumulative_amount
                        ) VALUES (
                            :ticker, :date, :time, :open, :high, :low, :close, :volume, :amount, :cumulative_amount
                        )
                        ON CONFLICT(ticker, date, time) DO UPDATE SET
                            amount = CASE
                                WHEN excluded.amount IS NOT NULL THEN excluded.amount
                                WHEN (minute_ohlcv.open, minute_ohlcv.high, minute_ohlcv.low,
                                      minute_ohlcv.close, minute_ohlcv.volume) =
                                     (excluded.open, excluded.high, excluded.low, excluded.close, excluded.volume)
                                     AND (excluded.cumulative_amount IS NULL OR
                                          excluded.cumulative_amount = minute_ohlcv.cumulative_amount)
                                THEN minute_ohlcv.amount
                                ELSE NULL END,
                            cumulative_amount = CASE
                                WHEN excluded.cumulative_amount IS NULL AND
                                     (minute_ohlcv.open, minute_ohlcv.high, minute_ohlcv.low,
                                      minute_ohlcv.close, minute_ohlcv.volume) =
                                     (excluded.open, excluded.high, excluded.low, excluded.close, excluded.volume)
                                THEN minute_ohlcv.cumulative_amount
                                ELSE excluded.cumulative_amount END,
                            open=excluded.open, high=excluded.high, low=excluded.low,
                            close=excluded.close, volume=excluded.volume
                    """
                    cursor.executemany(insert_sql, records)
                    cumulative = cursor.execute(
                        "SELECT cumulative_amount FROM minute_ohlcv WHERE ticker=? AND date=? AND time=?",
                        (ticker, last["date"], last["time"]),
                    ).fetchone()[0]
                    if previous is not None and previous[0] != cumulative:
                        successor = cursor.execute(
                            "SELECT time, cumulative_amount FROM minute_ohlcv WHERE ticker=? AND date=? AND time>? ORDER BY time LIMIT 1",
                            (ticker, last["date"], last["time"]),
                        ).fetchone()
                        if successor is not None:
                            next_time = (
                                datetime.strptime(last["dt_str"], "%Y%m%d%H%M%S")
                                + timedelta(minutes=1)
                            ).strftime("%H%M%S")
                            amount = None
                            if (
                                int(next_time) == successor[0]
                                and cumulative is not None
                                and successor[1] is not None
                            ):
                                amount = successor[1] - cumulative
                                if amount < 0:
                                    raise ValueError("Invalid cumulative minute amount")
                            cursor.execute(
                                "UPDATE minute_ohlcv SET amount=? WHERE ticker=? AND date=? AND time=?",
                                (amount, ticker, last["date"], successor[0]),
                            )
                    conn.commit()
                    success_any = True
                except Exception as e:
                    logger.error(f"[{ticker}] DB Insert Error: {e}")
                    raise
                finally:
                    conn.close()

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

        if success_any:
            conn = connect_sqlite()
            ma_conn = connect_ma_db()
            try:
                rebuild_minute_ma_for_ticker(conn, ma_conn, ticker)
                system_state.set_ticker_ma_ready("minute", ticker, True)
            except Exception as e:
                ma_conn.rollback()
                logger.error(f"[{ticker}] Minute MA rebuild error: {e}")
                raise
            finally:
                conn.close()
                ma_conn.close()

        return success_any, newest_dt
    except BaseException:
        if success_any:
            system_state.set_ticker_ma_ready("minute", ticker, False)
        raise


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
                    if success and newest_dt:
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
        try:
            await queue.join()
        finally:
            for worker_task in workers:
                worker_task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

        logger.sched(
            f"[SCHED] Cycle Finished. Success: {success_count}, Fail: {fail_count}."
        )

        if single_cycle:
            logger.sched("Single cycle finished. Exiting minute scheduler (test mode).")
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
