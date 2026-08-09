import os
from pathlib import Path

from core.database import (
    connect_sqlite,
    sync_memory_to_disk,
    test_db_var,
    test_mem_var,
)
from fastapi import HTTPException
from services.admin_daily_service import verify_daily_integrity_service
from services.admin_minute_service import verify_minute_integrity_service
from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler
from tasks.minute_ohlcv_scheduler import (
    run_minute_ohlcv_scheduler,
)


async def test_daily_scheduler_integration_service():
    # 1. 원본 DB에서 무작위 3종목 추출
    conn_real = connect_sqlite()  # test_db_var is None => trading.db
    try:
        cursor_real = conn_real.cursor()
        cursor_real.execute("SELECT * FROM stock_codes ORDER BY RANDOM() LIMIT 3")
        target_stocks = [dict(row) for row in cursor_real.fetchall()]
        if not target_stocks:
            raise HTTPException(status_code=404, detail="No stocks found in real DB")
    finally:
        conn_real.close()

    # 2. ContextVar 설정하여 테스트 환경 완벽 격리 (Memory + Disk)
    test_db_path = str(Path(__file__).resolve().parents[2] / "data" / "test_trading.db")
    test_mem_uri = "file:test_daily_mem?mode=memory&cache=shared"

    for ext in ["", "-wal", "-shm"]:
        target = test_db_path + ext
        if os.path.exists(target):
            try:
                os.remove(target)
            except Exception:
                pass

    token_db = test_db_var.set(test_db_path)
    token_mem = test_mem_var.set(test_mem_uri)
    test_keepalive_conn = None
    try:
        # 이 커넥션은 테스트가 끝날 때까지 닫지 않아 메모리 DB의 증발을 막습니다.
        test_keepalive_conn = connect_sqlite()

        # 3. 테스트용 인메모리 DB 스키마 생성 및 종목 이식
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_ohlcv (
                    ticker TEXT NOT NULL,
                    date INTEGER NOT NULL,
                    open INTEGER NOT NULL,
                    high INTEGER NOT NULL,
                    low INTEGER NOT NULL,
                    close INTEGER NOT NULL,
                    volume INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    PRIMARY KEY (ticker, date)
                ) WITHOUT ROWID, STRICT
                """
            )
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_codes (
                    ticker TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    is_halted INTEGER DEFAULT 0
                )
                """
            )
            for s in target_stocks:
                cursor_test.execute(
                    "INSERT INTO stock_codes (ticker, name, market) VALUES (?, ?, ?)",
                    (s["ticker"], s["name"], s["market"]),
                )
            conn_test.commit()
        finally:
            conn_test.close()

        results = {"target_stocks": [s["ticker"] for s in target_stocks]}

        # 4. [검증 1] 콜드스타트
        await run_daily_ohlcv_scheduler(market="KOSPI")
        await run_daily_ohlcv_scheduler(market="KOSDAQ")

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step1_cold_start_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 5. [검증 2] 최근 30영업일 치 고의 삭제(슬라이싱) 후 복구 검증
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            for ticker in results["target_stocks"]:
                cursor_test.execute(
                    """
                    DELETE FROM daily_ohlcv
                    WHERE ticker = ? AND date IN (
                        SELECT date FROM daily_ohlcv WHERE ticker = ? ORDER BY date DESC LIMIT 30
                    )
                    """,
                    (ticker, ticker),
                )
            conn_test.commit()

            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step2_deleted_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 스케줄러 재구동하여 빈 공간(Gap) 복구 (조기 종료 백필)
        await run_daily_ohlcv_scheduler(market="KOSPI")
        await run_daily_ohlcv_scheduler(market="KOSDAQ")

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step2_recovered_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 6. [검증 3] 메모리 -> 물리 디스크 Sync 및 디스크 파일 검증
        conn_test = connect_sqlite()
        try:
            sync_memory_to_disk(mem_conn=conn_test)
        finally:
            conn_test.close()

        # 인메모리 라우팅을 잠시 해제하여, 물리 디스크 커넥션 확보
        test_mem_var.set(None)
        conn_disk = connect_sqlite()
        try:
            cursor_disk = conn_disk.cursor()
            cursor_disk.execute(
                "SELECT ticker, COUNT(*) FROM daily_ohlcv GROUP BY ticker"
            )
            results["step3_disk_sync_counts"] = dict(cursor_disk.fetchall())
        finally:
            conn_disk.close()
            test_mem_var.set(test_mem_uri)

        # 7. [검증 4] API 데이터와 1:1 무결성 비교
        kospi_count = sum(1 for s in target_stocks if s["market"] == "KOSPI")
        kosdaq_count = sum(1 for s in target_stocks if s["market"] == "KOSDAQ")

        verify_results = {}
        if kospi_count > 0:
            verify_results["KOSPI"] = await verify_daily_integrity_service(
                sample_size=kospi_count, market="KOSPI"
            )
        if kosdaq_count > 0:
            verify_results["KOSDAQ"] = await verify_daily_integrity_service(
                sample_size=kosdaq_count, market="KOSDAQ"
            )

        results["step4_integrity_verification"] = verify_results

        return results

    finally:
        if test_keepalive_conn:
            test_keepalive_conn.close()
        test_db_var.reset(token_db)
        test_mem_var.reset(token_mem)


async def test_minute_scheduler_integration_service():
    # 1. 원본 DB에서 무작위 3종목 추출
    conn_real = connect_sqlite()
    try:
        cursor_real = conn_real.cursor()
        cursor_real.execute("SELECT * FROM stock_codes ORDER BY RANDOM() LIMIT 3")
        target_stocks = [dict(row) for row in cursor_real.fetchall()]
        if not target_stocks:
            raise HTTPException(status_code=404, detail="No stocks found in real DB")
    finally:
        conn_real.close()

    test_db_path = str(Path(__file__).resolve().parents[2] / "data" / "test_trading.db")
    test_mem_uri = "file:test_minute_mem?mode=memory&cache=shared"

    for ext in ["", "-wal", "-shm"]:
        target = test_db_path + ext
        if os.path.exists(target):
            try:
                os.remove(target)
            except Exception:
                pass

    token_db = test_db_var.set(test_db_path)
    token_mem = test_mem_var.set(test_mem_uri)
    test_keepalive_conn = None
    try:
        # 이 커넥션은 테스트가 끝날 때까지 닫지 않아 메모리 DB의 증발을 막습니다.
        test_keepalive_conn = connect_sqlite()

        # 스키마 초기화
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS minute_ohlcv (
                    ticker TEXT NOT NULL,
                    date INTEGER NOT NULL,
                    time INTEGER NOT NULL,
                    open INTEGER NOT NULL,
                    high INTEGER NOT NULL,
                    low INTEGER NOT NULL,
                    close INTEGER NOT NULL,
                    volume INTEGER NOT NULL,
                    amount INTEGER,
                    PRIMARY KEY (ticker, date, time)
                ) WITHOUT ROWID, STRICT
                """
            )
            cursor_test.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_codes (
                    ticker TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    is_halted INTEGER DEFAULT 0
                )
                """
            )
            for s in target_stocks:
                cursor_test.execute(
                    "INSERT INTO stock_codes (ticker, name, market) VALUES (?, ?, ?)",
                    (s["ticker"], s["name"], s["market"]),
                )
            conn_test.commit()
        finally:
            conn_test.close()

        results = {"target_stocks": [s["ticker"] for s in target_stocks]}

        # 4. [검증 1] 콜드스타트 백필 실행
        await run_minute_ohlcv_scheduler(
            markets=["KOSPI", "KOSDAQ"], single_cycle=True, priority=2
        )

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step1_cold_start_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 5. [검증 2] 최근 30개 분봉 고의 삭제 후 복구 검증
        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            for ticker in results["target_stocks"]:
                cursor_test.execute(
                    """
                    DELETE FROM minute_ohlcv
                    WHERE ticker = ? AND (date || time) IN (
                        SELECT date || time FROM minute_ohlcv WHERE ticker = ? ORDER BY date DESC, time DESC LIMIT 30
                    )
                    """,
                    (ticker, ticker),
                )
            conn_test.commit()

            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step2_deleted_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 갭필 복구
        await run_minute_ohlcv_scheduler(
            markets=["KOSPI", "KOSDAQ"], single_cycle=True, priority=2
        )

        conn_test = connect_sqlite()
        try:
            cursor_test = conn_test.cursor()
            cursor_test.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step2_recovered_counts"] = dict(cursor_test.fetchall())
        finally:
            conn_test.close()

        # 6. [검증 3] 메모리 -> 물리 디스크 Sync 및 디스크 파일 검증
        conn_test = connect_sqlite()
        try:
            sync_memory_to_disk(mem_conn=conn_test)
        finally:
            conn_test.close()

        test_mem_var.set(None)
        conn_disk = connect_sqlite()
        try:
            cursor_disk = conn_disk.cursor()
            cursor_disk.execute(
                "SELECT ticker, COUNT(*) FROM minute_ohlcv GROUP BY ticker"
            )
            results["step3_disk_sync_counts"] = dict(cursor_disk.fetchall())
        finally:
            conn_disk.close()
            test_mem_var.set(test_mem_uri)

        # 7. [검증 4] API 데이터와 1:1 무결성 비교
        kospi_count = sum(1 for s in target_stocks if s["market"] == "KOSPI")
        kosdaq_count = sum(1 for s in target_stocks if s["market"] == "KOSDAQ")

        verify_results = {}
        if kospi_count > 0:
            verify_results["KOSPI"] = await verify_minute_integrity_service(
                sample_size=kospi_count, market="KOSPI"
            )
        if kosdaq_count > 0:
            verify_results["KOSDAQ"] = await verify_minute_integrity_service(
                sample_size=kosdaq_count, market="KOSDAQ"
            )

        results["step4_integrity_verification"] = verify_results

        return results

    finally:
        if test_keepalive_conn:
            test_keepalive_conn.close()
        test_db_var.reset(token_db)
        test_mem_var.reset(token_mem)
