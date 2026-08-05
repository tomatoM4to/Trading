import asyncio
import logging
import threading

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.kis_auth import auth

logger = logging.getLogger(__name__)


class SystemScheduler:
    """통합 스케줄러.
    1 OCPU, 1GB RAM 환경의 최적화를 위해 단일 AsyncIOScheduler를 사용하여
    인증, 마스터 데이터 갱신 등 앱 전체의 예약된 작업들을 중앙 통제합니다.
    Thread-safe Singleton으로 구현됩니다.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self.scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
        self._is_running = False
        self._bg_auth_task: asyncio.Task[None] | None = None
        self._initialized = True

    def start(self) -> None:
        """스케줄러를 시작하고 각 Job을 등록한다."""
        if self._is_running:
            return

        # 1. 매일 밤 10시(22:00) 인증 갱신
        self.scheduler.add_job(
            self.refresh_auth_job,
            trigger="cron",
            hour=22,
            minute=0,
            id="refresh_auth_daily_2200",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # 2. 매일 오전 08시 30분 마스터 데이터(종목 리스트) 갱신
        self.scheduler.add_job(
            self.refresh_stock_codes_job,
            trigger="cron",
            hour=8,
            minute=30,
            id="refresh_stock_codes_daily_0830",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # 3. 매주 평일(월-금) 08:55 분봉 스케줄러 시작 (15:55 자체 종료)
        self.scheduler.add_job(
            self.start_minute_scheduler_job,
            trigger="cron",
            day_of_week="mon-fri",
            hour=8,
            minute=55,
            id="start_minute_scheduler_0855",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # 4. 매일 밤 23:00 일/분봉 가비지 컬렉션 (For Loop Chunking GC)
        self.scheduler.add_job(
            self.cleanup_ohlcv_job,
            trigger="cron",
            hour=23,
            minute=0,
            id="cleanup_ohlcv_gc_2300",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        # 5. 매일 오후 16:00 일봉 데이터 정규 업데이트 (KOSPI & KOSDAQ)
        self.scheduler.add_job(
            self.run_daily_ohlcv_job,
            trigger="cron",
            hour=16,
            minute=0,
            id="run_daily_ohlcv_1600",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

        self.scheduler.start()
        self._is_running = True
        logger.sched("System scheduler started")

    def stop(self) -> None:
        """스케줄러와 백그라운드 태스크를 종료한다."""
        if not self._is_running:
            return

        if self._bg_auth_task and not self._bg_auth_task.done():
            self._bg_auth_task.cancel()

        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.sched("System scheduler stopped")

    async def refresh_auth_job(self, force: bool = False) -> None:
        """실제 인증 작업을 수행하는 스케줄러 Job."""
        try:
            await asyncio.to_thread(auth, force=force)
            logger.sched("Background auth refresh completed (force=%s)", force)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Background auth refresh failed: %s", e)

    async def refresh_stock_codes_job(self) -> None:
        """종목 마스터 데이터를 갱신하는 스케줄러 Job."""
        # 동적 임포트를 사용하여 순환 참조 방지
        from tasks.init_stock_codes import init_stock_codes_db

        try:
            logger.sched("Starting scheduled stock codes refresh...")
            await asyncio.to_thread(init_stock_codes_db)
            logger.sched("Scheduled stock codes refresh completed.")
            
            from core.database import sync_memory_to_disk
            await asyncio.to_thread(sync_memory_to_disk)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Scheduled stock codes refresh failed: %s", e)

    async def start_minute_scheduler_job(self) -> None:
        """장중 분봉 수집 스케줄러를 시작하는 Job."""
        from tasks.minute_ohlcv_scheduler import run_minute_ohlcv_scheduler

        try:
            logger.sched("Starting scheduled minute OHLCV collector...")
            # 분봉 수집기는 15:55까지 무한루프를 돌며 작동함
            await run_minute_ohlcv_scheduler()
            logger.sched("Scheduled minute OHLCV collector finished naturally.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Scheduled minute OHLCV collector failed: %s", e)

    async def cleanup_ohlcv_job(self) -> None:
        """오후 11시(23:00) 일봉/분봉 가비지 컬렉션 (Time-based Bulk GC).
        일봉은 300일 이전, 분봉은 7일 이전 데이터를 단일 쿼리로 일괄 삭제합니다.
        """
        from core.database import connect_sqlite

        try:
            logger.sched("Starting OHLCV garbage collection (Time-based Bulk GC)...")

            def _run_gc():
                conn = connect_sqlite()
                try:
                    cursor = conn.cursor()

                    # 1. 일봉 GC: 300일 경과 데이터 일괄 삭제 (YYYYMMDD 형식 비교)
                    cursor.execute(
                        "DELETE FROM daily_ohlcv WHERE date < strftime('%Y%m%d', 'now', 'localtime', '-300 days')"
                    )
                    total_daily_deleted = cursor.rowcount

                    # 2. 분봉 GC: 7일 경과 데이터 일괄 삭제 (YYYYMMDD 형식 비교)
                    cursor.execute(
                        "DELETE FROM minute_ohlcv WHERE date < strftime('%Y%m%d', 'now', 'localtime', '-7 days')"
                    )
                    total_minute_deleted = cursor.rowcount

                    conn.commit()
                    return total_daily_deleted, total_minute_deleted
                finally:
                    conn.close()

            daily_del, minute_del = await asyncio.to_thread(_run_gc)
            logger.sched(
                f"OHLCV GC completed. Deleted daily: {daily_del} rows, minute: {minute_del} rows."
            )
            
            from core.database import sync_memory_to_disk
            await asyncio.to_thread(sync_memory_to_disk)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("OHLCV GC failed: %s", e)

    async def run_daily_ohlcv_job(self) -> None:
        """오후 4시 정규 일봉 데이터 업데이트 Job."""
        from tasks.daily_ohlcv_scheduler import run_daily_ohlcv_scheduler

        try:
            logger.sched("Starting scheduled daily OHLCV update (KOSPI & KOSDAQ)...")
            await run_daily_ohlcv_scheduler("KOSPI")
            await run_daily_ohlcv_scheduler("KOSDAQ")
            logger.sched("Scheduled daily OHLCV update completed.")
            
            from core.database import sync_memory_to_disk
            await asyncio.to_thread(sync_memory_to_disk)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Scheduled daily OHLCV update failed: %s", e)
