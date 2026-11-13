import json
import threading
import time
from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import patch

import requests

from tests.support import FrozenDateTime


def response(rows=None, *, status=200, rt_cd="0", output="output2"):
    res = requests.Response()
    res.status_code = status
    res._content = json.dumps(
        {
            "rt_cd": rt_cd,
            "msg_cd": "FIXTURE",
            "msg1": "fixture response",
            output: rows or [],
        }
    ).encode()
    res.headers["content-type"] = "application/json"
    return res


@dataclass
class Call:
    url: str
    params: dict
    start: float
    end: float | None = None
    timeout: int | None = None
    tr_id: str | None = None


class FakeTransport:
    def __init__(self, replies, gate=None):
        self.replies = deque(replies)
        self.calls = []
        self.entered = threading.Event()
        self.gate = gate
        self.stack = ExitStack()

    def __enter__(self):
        self.stack.enter_context(patch("requests.get", self.send))
        self.stack.enter_context(patch("requests.post", self.send))
        self.stack.enter_context(
            patch("tasks.daily_ohlcv_scheduler.datetime", FrozenDateTime)
        )
        self.stack.enter_context(
            patch("tasks.minute_ohlcv_scheduler.datetime", FrozenDateTime)
        )
        return self

    def __exit__(self, *args):
        if self.gate is not None:
            self.gate.set()
        return self.stack.__exit__(*args)

    def send(self, url, *, headers=None, params=None, timeout=None, **kwargs):
        call = Call(
            url,
            dict(params or {}),
            time.perf_counter(),
            timeout=timeout,
            tr_id=(headers or {}).get("tr_id"),
        )
        self.calls.append(call)
        self.entered.set()
        try:
            if self.gate is not None and len(self.calls) == 1:
                if not self.gate.wait(3):
                    raise AssertionError("Fake transport gate timed out")
            if not self.replies:
                raise AssertionError("Unexpected extra HTTP call beyond fixture budget")
            reply = self.replies.popleft()
            if isinstance(reply, Exception):
                raise reply
            if callable(reply):
                return reply(call)
            return reply
        finally:
            call.end = time.perf_counter()
