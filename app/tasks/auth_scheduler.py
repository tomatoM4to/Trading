import asyncio
import logging
import threading

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.kis_auth import auth

logger = logging.getLogger(__name__)


class AuthScheduler:
    """KIS 인증을 백그라운드에서 주기적으로 갱신하는 스케줄러. Thread-safe Singleton."""

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
        self._bg_task: asyncio.Task[None] | None = None
        self._initialized = True

    def start(self) -> None:
        """매일 밤 10시에 인증을 수행하고, 부팅 시 즉시 1회 인증을 시도한다."""
        if self._is_running:
            return

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
        self.scheduler.start()

        # 서버 부팅 직후 인증 상태를 보장하기 위해 즉시 1회 수행
        self._bg_task = asyncio.create_task(self.refresh_auth_job(force=True))
        self._is_running = True
        logger.info("Auth scheduler started")

    def stop(self) -> None:
        """스케줄러와 백그라운드 인증 태스크를 종료한다."""
        if not self._is_running:
            return

        if self._bg_task and not self._bg_task.done():
            self._bg_task.cancel()
        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("Auth scheduler stopped")

    async def refresh_auth_job(self, force: bool = False) -> None:
        """실제 인증 작업을 수행하는 스케줄러 Job."""
        try:
            await asyncio.to_thread(auth)
            logger.info("Background auth refresh completed (force=%s)", force)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Background auth refresh failed: %s", e)
