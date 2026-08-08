import asyncio
import logging

from core.database import connect_sqlite, connect_ma_db
from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
from tasks.init_stock_codes import init_stock_codes_db
from core.ma_calculator import ma_calculator

logger = logging.getLogger(__name__)


async def rebuild_ma_database():
    """디스크 DB의 OHLCV를 읽어와 In-Memory MA 테이블을 셋업합니다."""
    logger.sched("[Bootstrap] Starting MA Database Rebuild (Cold Start)...")
    ma_calculator.clear()
    
    disk_conn = connect_sqlite()
    ma_conn = connect_ma_db()
    
    try:
        # 1. 기존 In-Memory MA 테이블 초기화 (08:00 리셋 대비)
        ma_conn.execute("DELETE FROM daily_ma")
        ma_conn.execute("DELETE FROM minute_ma")
        
        # 2. 일봉 MA 리빌드
        logger.sched("[Bootstrap] Rebuilding daily_ma from disk...")
        cursor = disk_conn.execute("SELECT ticker, date, close FROM daily_ohlcv ORDER BY date ASC")
        
        ma_records = []
        for row in cursor:
            ticker, date, close = row['ticker'], row['date'], row['close']
            ma_calculator.add_daily_close(ticker, close)
            res = ma_calculator.get_daily_ma(ticker)
            ma_records.append((ticker, date, res['ma5'], res['ma10'], res['ma20'], res['ma60'], res['ma120'], res['ma200']))
            
            if len(ma_records) >= 10000:
                ma_conn.executemany("INSERT OR IGNORE INTO daily_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ma_records)
                ma_records.clear()
        if ma_records:
            ma_conn.executemany("INSERT OR IGNORE INTO daily_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ma_records)
            ma_records.clear()
        ma_conn.commit()
        
        # 3. 분봉 MA 리빌드 (최근 3일치만 가져와서 연산 - 앞의 199개는 예열용으로 사용됨)
        logger.sched("[Bootstrap] Rebuilding minute_ma from disk (Recent 3 days)...")
        # 성능을 위해 최근 3일의 날짜를 먼저 구함
        dates_cursor = disk_conn.execute("SELECT DISTINCT date FROM minute_ohlcv ORDER BY date DESC LIMIT 3")
        recent_dates = [str(r['date']) for r in dates_cursor.fetchall()]
        
        if recent_dates:
            placeholders = ",".join("?" for _ in recent_dates)
            query = f"""
                SELECT ticker, date, time, close 
                FROM minute_ohlcv 
                WHERE date IN ({placeholders})
                ORDER BY date ASC, time ASC
            """
            cursor = disk_conn.execute(query, recent_dates)
            
            for row in cursor:
                ticker, date, time, close = row['ticker'], row['date'], row['time'], row['close']
                ma_calculator.add_minute_close(ticker, close)
                res = ma_calculator.get_minute_ma(ticker)
                ma_records.append((ticker, date, time, res['ma5'], res['ma10'], res['ma20'], res['ma60'], res['ma120'], res['ma200']))
                
                if len(ma_records) >= 10000:
                    ma_conn.executemany("INSERT OR IGNORE INTO minute_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ma_records)
                    ma_records.clear()
            if ma_records:
                ma_conn.executemany("INSERT OR IGNORE INTO minute_ma VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ma_records)
            ma_conn.commit()
            
        logger.sched("[Bootstrap] MA Database Rebuild Complete.")
    except Exception as e:
        logger.error(f"[Bootstrap] Failed to rebuild MA database: {e}")
    finally:
        disk_conn.close()
        ma_conn.close()
async def run_bootstrap_pipeline():
    """
    서버 구동 시 DB 빈 상태를 감지하여
    마스터 데이터 -> 일봉 데이터 순으로 순차(Sequential) 실행하는 파이프라인.
    이 함수는 FastAPI 서버 기동 후 백그라운드에서 단 1회 실행됩니다.
    """
    logger.sched("=== Starting Bootstrap Pipeline ===")

    # 1. 마스터 데이터 (stock_codes)
    stock_count = 0
    conn = connect_sqlite()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_codes'"
        )
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM stock_codes")
            stock_count = cursor.fetchone()[0]
        else:
            stock_count = 0
    except Exception as e:
        logger.error(f"Failed to check stock_codes: {e}")
    finally:
        conn.close()

    if stock_count == 0:
        logger.sched("[Bootstrap] stock_codes is empty. Initializing...")
        try:
            # 동기 함수이므로 asyncio.to_thread로 래핑하여 실행
            await asyncio.to_thread(init_stock_codes_db)
            logger.sched("[Bootstrap] stock_codes initialized.")
        except Exception as e:
            logger.error(f"[Bootstrap] Failed to initialize stock_codes: {e}")
            return  # 마스터 데이터가 없으면 뒤의 작업도 불가능하므로 중단
    else:
        logger.sched(
            f"[Bootstrap] stock_codes already exists ({stock_count} rows). Skipping."
        )

    # 2. 일봉 데이터 (daily_ohlcv)
    # KOSPI, KOSDAQ 순차 실행
    for market in ["KOSPI", "KOSDAQ"]:
        ohlcv_count = 0
        conn = connect_sqlite()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM daily_ohlcv d JOIN stock_codes s ON d.ticker = s.ticker WHERE s.market = ?",
                (market,),
            )
            ohlcv_count = cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to check daily_ohlcv for {market}: {e}")
        finally:
            conn.close()

        if ohlcv_count < 100:
            logger.sched(
                f"[Bootstrap] daily_ohlcv for {market} seems empty ({ohlcv_count} rows). Initializing (Cold Start)..."
            )
        else:
            logger.sched(
                f"[Bootstrap] daily_ohlcv for {market} already exists ({ohlcv_count} rows). Checking for missing gaps..."
            )

        try:
            # 여기서 await를 걸었기 때문에, 일봉 적재가 완전히 끝날 때까지 다음 단계로 안 넘어감
            await run_daily_ohlcv_scheduler(market)
            logger.sched(f"[Bootstrap] daily_ohlcv for {market} synchronized.")
        except Exception as e:
            logger.error(
                f"[Bootstrap] Failed to synchronize daily_ohlcv for {market}: {e}"
            )

    # 3. 인메모리 MA DB 리빌드 파이프라인 실행
    await rebuild_ma_database()

    # 4. 분봉 데이터 스케줄러 기동 (단일 Unified 스케줄러)
    from tasks.minute_ohlcv_scheduler import start_minute_scheduler_task

    logger.sched(
        "[Bootstrap] Starting unified real-time minute OHLCV scheduler in background..."
    )
    await start_minute_scheduler_task()

    # 4. 수급 데이터 (추후 연동)

    logger.sched("=== Bootstrap Pipeline Finished ===")
