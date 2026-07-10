import asyncio
import logging

from core.database import connect_sqlite
from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
from tasks.init_stock_codes import init_stock_codes_db

logger = logging.getLogger(__name__)


async def run_bootstrap_pipeline():
    """
    서버 구동 시 DB 빈 상태를 감지하여
    마스터 데이터 -> 일봉 데이터 순으로 순차(Sequential) 실행하는 파이프라인.
    이 함수는 FastAPI 서버 기동 후 백그라운드에서 단 1회 실행됩니다.
    """
    logger.info("=== Starting Bootstrap Pipeline ===")

    # 1. 마스터 데이터 (stock_codes)
    stock_count = 0
    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stock_codes")
        stock_count = cursor.fetchone()[0]
    except Exception as e:
        logger.error(f"Failed to check stock_codes: {e}")
    finally:
        conn.close()

    if stock_count == 0:
        logger.info("[Bootstrap] stock_codes is empty. Initializing...")
        try:
            # 동기 함수이므로 asyncio.to_thread로 래핑하여 실행
            await asyncio.to_thread(init_stock_codes_db)
            logger.info("[Bootstrap] stock_codes initialized.")
        except Exception as e:
            logger.error(f"[Bootstrap] Failed to initialize stock_codes: {e}")
            return  # 마스터 데이터가 없으면 뒤의 작업도 불가능하므로 중단
    else:
        logger.info(f"[Bootstrap] stock_codes already exists ({stock_count} rows). Skipping.")

    # 2. 일봉 데이터 (daily_ohlcv)
    # KOSPI, KOSDAQ 순차 실행
    for market in ["KOSPI", "KOSDAQ"]:
        ohlcv_count = 0
        conn = connect_sqlite()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM daily_ohlcv d JOIN stock_codes s ON d.ticker = s.ticker WHERE s.market = ?",
                (market,)
            )
            ohlcv_count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to check daily_ohlcv for {market}: {e}")
        finally:
            conn.close()

        # 데이터가 비어있거나, 종목 수보다 터무니없이 적을 경우 초기화 대상
        if ohlcv_count < 100:
            logger.info(f"[Bootstrap] daily_ohlcv for {market} seems empty ({ohlcv_count} rows). Initializing...")
            try:
                # 여기서 await를 걸었기 때문에, 일봉 적재가 완전히 끝날 때까지 다음 단계로 안 넘어감
                await run_daily_ohlcv_scheduler(market)
                logger.info(f"[Bootstrap] daily_ohlcv for {market} initialized.")
            except Exception as e:
                logger.error(f"[Bootstrap] Failed to initialize daily_ohlcv for {market}: {e}")
        else:
            logger.info(f"[Bootstrap] daily_ohlcv for {market} already exists ({ohlcv_count} rows). Skipping.")

    # 3. 분봉 데이터 (추후 연동)
    # 4. 수급 데이터 (추후 연동)

    logger.info("=== Bootstrap Pipeline Finished ===")
