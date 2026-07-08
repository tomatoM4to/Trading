import logging
import os

from rich.console import Console
from rich.highlighter import RegexHighlighter
from rich.logging import RichHandler


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
        r"(?P<app_tag>\[APP\])",
    ]


def setup_logging() -> None:
    """Configure root logger with a simpler Rich handler for performance."""
    # 기본 로그 레벨을 WARNING으로 상향하여 일반적인 INFO 로그가 디스크 I/O를 유발하지 않게 함
    level_name = os.getenv("LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)

    console = Console(stderr=True)
    handler = RichHandler(
        console=console,
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
