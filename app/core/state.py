import threading
from contextlib import contextmanager


class SystemState:
    """통합 글로벌 시스템 상태 관리 싱글톤 객체.
    무거운 작업(GC, 부트스트랩, 싱크 등) 시 API 접근을 원천 차단하기 위해 사용.
    """

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._lock = threading.Lock()
        self._is_available = True
        self._reason = ""
        self._acquire_count = 0
        self._initialized = True

    @property
    def status(self) -> tuple[bool, str]:
        """현재 시스템의 (가용여부, 거절사유) 반환"""
        with self._lock:
            return self._is_available, self._reason

    @contextmanager
    def acquire(self, reason: str):
        """특정 작업(reason)을 수행하기 위해 글로벌 락을 획득하고 API 접근을 차단함"""
        with self._lock:
            # 최초 획득 시에만 상태를 변경하고 사유를 기록함
            if self._acquire_count == 0:
                self._is_available = False
                self._reason = reason
            self._acquire_count += 1
        try:
            yield
        finally:
            with self._lock:
                self._acquire_count -= 1
                # 모든 락이 해제되었을 때만 가용 상태로 복구함
                if self._acquire_count == 0:
                    self._is_available = True
                    self._reason = ""


# 전역 상태 객체
system_state = SystemState()
