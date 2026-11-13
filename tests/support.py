import atexit
import builtins
import importlib
import io
import json
import logging
import os
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, chdir
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
SESSION = tempfile.TemporaryDirectory(prefix="trading-harness-")
SESSION_PATH = Path(SESSION.name).resolve()
CONNECTIONS = []
ALLOWED_MEMORY = {":memory:"}
BLOCKED = []
_connect = sqlite3.connect
_open = builtins.open
_socket_connect = socket.socket.connect
SAFETY = ExitStack()
SYNTHETIC_CONFIG = {
    "my_app": "fixture-app",
    "my_sec": "fixture-secret",
    "my_htsid": "fixture",
    "my_acct_stock": "00000000",
    "my_prod": "01",
    "my_token": "",
    "prod": "https://fixture.invalid",
    "ops": "ws://fixture.invalid",
    "vps": "https://fixture.invalid",
    "vops": "ws://fixture.invalid",
    "my_agent": "offline-harness",
}


def blocked_network(*args, **kwargs):
    BLOCKED.append("network")
    raise AssertionError("Offline harness blocked network access")


def guarded_socket_connect(sock, address):
    caller = sys._getframe(1)
    if (
        caller.f_globals.get("__name__") == "socket"
        and caller.f_code.co_name == "_fallback_socketpair"
    ):
        return _socket_connect(sock, address)
    return blocked_network()


def safe_open(file, *args, **kwargs):
    if isinstance(file, (str, os.PathLike)):
        if Path(file).resolve() == ROOT / "kis_devlp.yaml":
            return io.StringIO(json.dumps(SYNTHETIC_CONFIG))
    return _open(file, *args, **kwargs)


def allowed_target(target):
    value = os.fsdecode(target)
    if value in ALLOWED_MEMORY:
        return True
    if value.startswith("file:"):
        return False
    return Path(value).resolve().is_relative_to(SESSION_PATH)


class TrackedConnection(sqlite3.Connection):
    closed = False

    def close(self):
        super().close()
        self.closed = True


def guarded_connect(database, *args, **kwargs):
    if not allowed_target(database):
        BLOCKED.append("database")
        raise AssertionError("Offline harness blocked DB outside its temporary root")
    kwargs.setdefault("factory", TrackedConnection)
    conn = _connect(database, *args, **kwargs)
    conn.set_authorizer(
        lambda action, arg1, arg2, db, trigger: (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_ATTACH and not allowed_target(arg1)
            else sqlite3.SQLITE_OK
        )
    )
    CONNECTIONS.append(conn)
    return conn


SAFETY.enter_context(patch("builtins.open", safe_open))
SAFETY.enter_context(patch("socket.socket.connect", guarded_socket_connect))
SAFETY.enter_context(patch("socket.socket.connect_ex", blocked_network))
SAFETY.enter_context(patch("socket.create_connection", blocked_network))
SAFETY.enter_context(patch("sqlite3.connect", guarded_connect))
SAFETY.enter_context(
    patch.dict(
        os.environ,
        {
            "SQLITE_DB_PATH": str(SESSION_PATH / "unconfigured.db"),
            "SCHED": "False",
            "DEBUG": "True",
            "ADMIN_API_KEY": "fixture-admin",
        },
    )
)

SAFETY.enter_context(
    patch.object(requests.sessions.Session, "request", blocked_network)
)

database = importlib.import_module("core.database")
kis_auth = importlib.import_module("core.kis_auth")
importlib.import_module("core.logging")

logging.disable(logging.CRITICAL)
kis_auth._kis_env = kis_auth._kis_cfg.to_environment("01", "fixture-token")


def shutdown_safety():
    for conn in CONNECTIONS:
        if not conn.closed:
            conn.close()
    SAFETY.close()
    SESSION.cleanup()


atexit.register(shutdown_safety)


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 12, 15, 30, tzinfo=tz)


class Sandbox:
    def __init__(self):
        self.stack = ExitStack()
        self.path = SESSION_PATH / uuid4().hex
        self.path.mkdir()
        self.stack.enter_context(chdir(self.path))
        self.disk = self.path / "canonical.db"
        self.ma_uri = f"file:harness_{uuid4().hex}?mode=memory&cache=shared"
        ALLOWED_MEMORY.add(self.ma_uri)
        self.start_connections = len(CONNECTIONS)
        self.stack.enter_context(
            patch.dict(os.environ, {"SQLITE_DB_PATH": str(self.disk)})
        )
        self.stack.enter_context(patch.object(database, "_MA_MEM_DB_URI", self.ma_uri))
        self.stack.enter_context(patch.object(database, "_keepalive_ma_conn", None))
        self.db_token = database.test_db_var.set(str(self.disk))
        self.mem_token = database.test_mem_var.set(None)
        database.init_sqlite_connection()

    def rows(self, table):
        if table not in {
            "daily_ohlcv",
            "minute_ohlcv",
            "daily_ma",
            "minute_ma",
            "stock_codes",
        }:
            raise ValueError(table)
        conn = (
            database.connect_ma_db()
            if table.endswith("_ma")
            else database.connect_sqlite()
        )
        try:
            return [
                tuple(r)
                for r in conn.execute(
                    f"SELECT * FROM {table} ORDER BY 1, 2"
                    + (", 3" if table.startswith("minute") else "")
                )
            ]
        finally:
            conn.close()

    def write(self, sql, records=()):
        conn = database.connect_sqlite()
        try:
            if records:
                conn.executemany(sql, records)
            else:
                conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def stock(self, ticker="A", halted=0, admin=0):
        self.write(
            "INSERT INTO stock_codes (ticker,name,market,is_halted,is_admin_issue) VALUES (?,?,?,?,?)",
            [(ticker, ticker, "KOSPI", halted, admin)],
        )

    def close(self):
        database._keepalive_ma_conn.close()
        leaked = [c for c in CONNECTIONS[self.start_connections :] if not c.closed]
        for conn in leaked:
            conn.close()
        database.test_mem_var.reset(self.mem_token)
        database.test_db_var.reset(self.db_token)
        self.stack.close()
        ALLOWED_MEMORY.remove(self.ma_uri)
        if leaked:
            raise AssertionError(f"{len(leaked)} SQLite connections leaked")


class DatabaseCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.blocked_count = len(BLOCKED)
        self.box = Sandbox()
        self.addCleanup(self.box.close)

    async def asyncTearDown(self):
        from core.kis_fetch import stop_q_worker

        await stop_q_worker()
        self.assertEqual(
            len(BLOCKED),
            self.blocked_count,
            "Unexpected unsafe I/O was attempted during the test",
        )


def fixture(name):
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
