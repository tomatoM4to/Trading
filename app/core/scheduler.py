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

        self.scheduler.start()

        # 서버 부팅 직후 인증 상태를 보장하기 위해 즉시 1회 수행
        self._bg_auth_task = asyncio.create_task(self.refresh_auth_job(force=True))
        self._is_running = True
        logger.info("System scheduler started")

    def stop(self) -> None:
        """스케줄러와 백그라운드 태스크를 종료한다."""
        if not self._is_running:
            return

        if self._bg_auth_task and not self._bg_auth_task.done():
            self._bg_auth_task.cancel()

        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("System scheduler stopped")

    async def refresh_auth_job(self, force: bool = False) -> None:
        """실제 인증 작업을 수행하는 스케줄러 Job."""
        try:
            await asyncio.to_thread(auth)
            logger.info("Background auth refresh completed (force=%s)", force)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Background auth refresh failed: %s", e)

    async def refresh_stock_codes_job(self) -> None:
        """종목 마스터 데이터를 갱신하는 스케줄러 Job."""
        # 동적 임포트를 사용하여 순환 참조 방지
        from tasks.init_stock_codes import init_stock_codes_db
        try:
            logger.info("Starting scheduled stock codes refresh...")
            await asyncio.to_thread(init_stock_codes_db)
            logger.info("Scheduled stock codes refresh completed.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Scheduled stock codes refresh failed: %s", e)
