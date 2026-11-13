import asyncio
import json
import threading
from unittest.mock import patch

import pytest
import requests

from tests.transport import FakeTransport, response


async def submit(label, priority=5):
    from core.kis_fetch import async_kis_fetch

    return await async_kis_fetch(
        "/fixture", "FIXTURE", "", {"label": label}, priority=priority
    )


async def entered(transport):
    if not await asyncio.to_thread(transport.entered.wait, 2):
        raise AssertionError("Queue never reached the fake transport")


async def cancel_all(tasks):
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


pytestmark = pytest.mark.stage3


async def test_priority_fifo_serialization_and_completion_spacing():
    gate = threading.Event()
    with FakeTransport([response()] * 5, gate=gate) as transport:
        tasks = [asyncio.create_task(submit("first"))]
        try:
            await entered(transport)
            tasks += [
                asyncio.create_task(submit(label, priority))
                for label, priority in [
                    ("low", 9),
                    ("high1", 1),
                    ("high2", 1),
                    ("medium", 5),
                ]
            ]
            await asyncio.sleep(0)
            gate.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 3)
        finally:
            gate.set()
            await cancel_all(tasks)
    assert [c.params["label"] for c in transport.calls] == [
        "first",
        "high1",
        "high2",
        "medium",
        "low",
    ]
    assert all(c.timeout == 10 for c in transport.calls)
    for previous, current in zip(transport.calls, transport.calls[1:], strict=False):
        assert current.start - previous.end >= 0.1


async def test_transport_timeout_and_broker_failure_leave_worker_usable():
    from core.kis_fetch import APIResp

    with FakeTransport([requests.Timeout("injected"), response(rt_cd="1"), response()]):
        with pytest.raises(requests.Timeout):
            await asyncio.wait_for(submit("timeout"), 2)
        failed = await asyncio.wait_for(submit("broker-error"), 2)
        assert not failed.is_ok()
        assert (await asyncio.wait_for(submit("after-error"), 2)).is_ok()
    malformed = response()
    malformed._content = b"not-json"
    assert not APIResp(malformed).is_ok()


async def test_cancelled_queued_request_is_not_sent():
    gate = threading.Event()
    tasks = []
    with FakeTransport([response()] * 3, gate=gate) as transport:
        try:
            tasks.append(asyncio.create_task(submit("first")))
            await entered(transport)
            cancelled = asyncio.create_task(submit("cancelled"))
            tasks.append(cancelled)
            await asyncio.sleep(0)
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
            tasks.append(asyncio.create_task(submit("last")))
            gate.set()
            await asyncio.wait_for(asyncio.gather(tasks[0], tasks[-1]), 2)
            labels = [c.params["label"] for c in transport.calls]
        finally:
            gate.set()
            await cancel_all(tasks)
    assert labels == ["first", "last"]


async def test_stop_resolves_active_and_waiting_callers():
    from core.kis_fetch import stop_q_worker

    gate = threading.Event()
    tasks = []
    with FakeTransport([response()] * 2, gate=gate) as transport:
        try:
            tasks.append(asyncio.create_task(submit("active")))
            await entered(transport)
            tasks.append(asyncio.create_task(submit("waiting")))
            await asyncio.sleep(0)
            await stop_q_worker()
            gate.set()
            await asyncio.sleep(0.02)
            resolved = [task.done() for task in tasks]
        finally:
            gate.set()
            await cancel_all(tasks)
    assert resolved == [True, True], "Stopped queue must not strand response Futures"


async def test_restart_does_not_overlap_still_running_transport():
    from core.kis_fetch import start_q_worker, stop_q_worker

    gate = threading.Event()
    tasks = []
    with FakeTransport([response()] * 2, gate=gate) as transport:
        try:
            tasks.append(asyncio.create_task(submit("old")))
            await entered(transport)
            await stop_q_worker()
            await start_q_worker()
            tasks.append(asyncio.create_task(submit("new")))
            await asyncio.sleep(0.15)
            gate.set()
            await asyncio.wait_for(tasks[-1], 2)
            await asyncio.to_thread(gate.wait, 1)
            for _ in range(100):
                if transport.calls[0].end is not None:
                    break
                await asyncio.sleep(0.005)
        finally:
            gate.set()
            await cancel_all(tasks)
    assert len(transport.calls) == 2
    assert transport.calls[1].start - transport.calls[0].end >= 0.1


async def test_idle_stop_restart_and_new_request():
    from core.kis_fetch import start_q_worker, stop_q_worker

    await start_q_worker()
    await stop_q_worker()
    with FakeTransport([response()]):
        assert (await submit("restarted")).is_ok()


def test_auth_failure_and_cache_expiration_use_real_auth_boundary(sandbox):
    from core import kis_auth

    root = sandbox.path / "tokens"
    root.mkdir()
    cache = root / f"KIS{__import__('datetime').datetime.today():%Y%m%d}"
    cache.write_text(
        "token: fixture-expired\nvalid-date: '2000-01-01 00:00:00'\n", encoding="utf-8"
    )
    with (
        patch.object(kis_auth, "config_root", root),
        patch.object(kis_auth, "_kis_env", None),
        FakeTransport([response(status=401)]) as transport,
    ):
        kis_auth.auth(force=False)
        assert kis_auth.get_kis_env() is None
        assert transport.calls[0].timeout == 30
    good = response()
    good._content = json.dumps(
        {
            "access_token": "fixture-token",
            "access_token_token_expired": "2099-01-01 00:00:00",
        }
    ).encode()
    with (
        patch.object(kis_auth, "config_root", root),
        patch.dict(kis_auth._base_headers),
        FakeTransport([good]) as transport,
    ):
        kis_auth.auth(force=True)
        kis_auth.auth(force=False)
        assert len(transport.calls) == 1
        assert transport.calls[0].timeout == 30
