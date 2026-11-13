from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import pytest_asyncio

from tests.metrics import peak_rss
from tests.support import OfflineEnvironment, Sandbox, load_fixture

OFFLINE = pytest.StashKey[OfflineEnvironment]()


def pytest_configure(config):
    stack = ExitStack()
    config.add_cleanup(stack.close)
    root = Path(stack.enter_context(TemporaryDirectory(prefix="trading-harness-")))
    config.stash[OFFLINE] = stack.enter_context(OfflineEnvironment(root))


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        f"Harness peak RSS: {peak_rss() / 1024**2:.1f} MiB "
        "(cumulative Python process; excludes crash subprocesses and OS page cache)"
    )


@pytest.fixture(scope="session")
def offline(pytestconfig):
    return pytestconfig.stash[OFFLINE]


@pytest_asyncio.fixture(autouse=True)
async def sandbox(offline):
    from core.kis_fetch import stop_q_worker

    blocked_count = len(offline.blocked)
    with Sandbox(offline) as box:
        try:
            yield box
        finally:
            await stop_q_worker()
            assert len(offline.blocked) == blocked_count, (
                "Unexpected unsafe I/O was attempted during the test"
            )


@pytest.fixture
def candles():
    return load_fixture("candles.json")
