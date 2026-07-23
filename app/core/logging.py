import logging
import os

from rich.console import Console
from rich.highlighter import RegexHighlighter
from rich.logging import RichHandler

SCHED_LEVEL = 25
logging.addLevelName(SCHED_LEVEL, "SCHED")


def sched(self, message, *args, **kws):
    if self.isEnabledFor(SCHED_LEVEL):
        self._log(SCHED_LEVEL, message, args, **kws)


logging.Logger.sched = sched


class LogCategoryFilter(logging.Filter):
    """Attach a category tag to each log record based on logger name."""

    def filter(self, record: logging.LogRecord) -> bool:
        source = " ".join(
            [
                record.name,
                getattr(record, "module", ""),
                getattr(record, "pathname", ""),
                record.getMessage(),  # Include the actual log message
            ]
        ).lower()

        if "auth" in source:
            record.category_tag = "[AUTH]"
        elif "scheduler" in source or "ohlcv" in source:
            record.category_tag = "[SCHED]"
        else:
            record.category_tag = "[APP]"
        return True


class LogCategoryHighlighter(RegexHighlighter):
    """Highlight category tags in different colors."""

    base_style = "logging.category."
    highlights = [
        r"(?P<auth_tag>\[AUTH\])",
        r"(?P<sched_tag>\[SCHED\])",
        r"(?P<trading_tag>\[TRADING\])",
        r"(?P<bootstrap_tag>\[Bootstrap\])",
        r"(?P<app_tag>\[APP\])",
    ]


def setup_logging() -> None:
    """Configure root logger with a simpler Rich handler for performance."""
    # 1. 묵언수행(Silence)할 외부 시끄러운 로거들 목록 (WARNING 레벨 이상만 출력)
    noisy_loggers = [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "apscheduler",
        "apscheduler.scheduler",
        "apscheduler.executors.default",
        "watchfiles",
        "watchfiles.main",
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # 2. 내 앱의 기본 로그 레벨 설정
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # 3. 색상 테마 정의
    from rich.theme import Theme

    custom_theme = Theme(
        {
            "logging.category.auth_tag": "bold green",
            "logging.category.sched_tag": "bold blue",
            "logging.category.trading_tag": "bold magenta",
            "logging.category.bootstrap_tag": "bold cyan",
            "logging.category.app_tag": "bold white",
        }
    )

    console = Console(stderr=True, theme=custom_theme)
    handler = RichHandler(
        console=console,
        highlighter=LogCategoryHighlighter(),
        rich_tracebacks=False,  # 트레이스백 생성 비용 제거
        show_time=False,  # 시간 출력 제외
        show_level=True,
        show_path=False,  # 파일 경로 출력 제외 (연산 비용 감소)
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
