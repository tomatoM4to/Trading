import builtins
import importlib
import io
import json
import logging
import os
import re
import socket
import sqlite3
import sys
from contextlib import ExitStack, chdir
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[1]
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


class TrackedConnection(sqlite3.Connection):
    closed = False
    bound_attach = False

    def execute(self, sql, parameters=(), /):
        if re.fullmatch(r"\s*ATTACH DATABASE \? AS \w+\s*", sql, re.IGNORECASE):
            if len(parameters) != 1 or not self.allowed_target(parameters[0]):
                raise AssertionError("Offline harness blocked bound ATTACH target")
            self.bound_attach = True
        try:
            return super().execute(sql, parameters)
        finally:
            self.bound_attach = False

    def close(self):
        super().close()
        self.closed = True


class OfflineEnvironment:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.connections = []
        self.memory_uris = {":memory:"}
        self.blocked = []
        self.stack = ExitStack()
        self.original_connect = sqlite3.connect
        self.original_open = builtins.open
        self.original_socket_connect = socket.socket.connect

    def block_network(self, *args, **kwargs):
        self.blocked.append("network")
        raise AssertionError("Offline harness blocked network access")

    def open(self, file, *args, **kwargs):
        if (
            isinstance(file, (str, os.PathLike))
            and Path(file).resolve() == ROOT / "kis_devlp.yaml"
        ):
            return io.StringIO(json.dumps(SYNTHETIC_CONFIG))
        return self.original_open(file, *args, **kwargs)

    def allowed_target(self, target):
        if target is None:
            return False
        value = os.fsdecode(target)
        if value in self.memory_uris:
            return True
        return not value.startswith("file:") and Path(value).resolve().is_relative_to(
            self.root
        )

    def connect(self, path, *args, **kwargs):
        if not self.allowed_target(path):
            self.blocked.append("database")
            raise AssertionError(
                "Offline harness blocked DB outside its temporary root"
            )
        kwargs.setdefault("factory", TrackedConnection)
        conn = self.original_connect(path, *args, **kwargs)
        conn.allowed_target = self.allowed_target
        conn.set_authorizer(
            lambda action, arg1, arg2, db, trigger: (
                sqlite3.SQLITE_DENY
                if action == sqlite3.SQLITE_ATTACH
                and not (
                    self.allowed_target(arg1) or (arg1 is None and conn.bound_attach)
                )
                else sqlite3.SQLITE_OK
            )
        )
        self.connections.append(conn)
        return conn

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True)

        def connect_socket(sock, address):
            caller = sys._getframe(1)
            if (
                caller.f_globals.get("__name__") == "socket"
                and caller.f_code.co_name == "_fallback_socketpair"
            ):
                return self.original_socket_connect(sock, address)
            return self.block_network()

        try:
            self.stack.enter_context(
                patch.object(sys, "path", [str(ROOT / "app"), *sys.path])
            )
            self.stack.enter_context(patch("builtins.open", self.open))
            self.stack.enter_context(patch("socket.socket.connect", connect_socket))
            self.stack.enter_context(
                patch("socket.socket.connect_ex", self.block_network)
            )
            self.stack.enter_context(
                patch("socket.create_connection", self.block_network)
            )
            self.stack.enter_context(patch("sqlite3.connect", self.connect))
            self.stack.enter_context(
                patch.object(requests.sessions.Session, "request", self.block_network)
            )
            self.stack.enter_context(
                patch.dict(
                    os.environ,
                    {
                        "SQLITE_DB_PATH": str(self.root / "unconfigured.db"),
                        "SCHED": "False",
                        "DEBUG": "True",
                        "ADMIN_API_KEY": "fixture-admin",
                    },
                )
            )
            self.database = importlib.import_module("core.database")
            self.auth = importlib.import_module("core.kis_auth")
            importlib.import_module("core.logging")
            self.stack.enter_context(
                patch.object(
                    self.auth,
                    "_kis_env",
                    self.auth._kis_cfg.to_environment("01", "fixture-token"),
                )
            )
            self.stack.enter_context(
                patch.object(self.auth, "config_root", self.root / "tokens")
            )
            self.previous_log_level = logging.root.manager.disable
            logging.disable(logging.CRITICAL)
            return self
        except BaseException:
            self.stack.close()
            raise

    def __exit__(self, *exc):
        try:
            for conn in self.connections:
                if not conn.closed:
                    conn.close()
        finally:
            logging.disable(self.previous_log_level)
            self.stack.close()


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 12, 15, 30, tzinfo=tz)


class Sandbox:
    def __init__(self, offline):
        self.offline = offline
        self.database = offline.database
        self.stack = ExitStack()
        self.path = offline.root / uuid4().hex
        self.path.mkdir()
        self.disk = self.path / "canonical.db"
        self.ma_uri = f"file:harness_{uuid4().hex}?mode=memory&cache=shared"

    def __enter__(self):
        database = self.database
        from core.state import system_state

        self.stack.enter_context(patch.object(system_state, "_ma_ready", False))
        self.stack.enter_context(
            patch.object(system_state, "_ma_reason", "이동평균 데이터 준비 중입니다.")
        )
        self.stack.enter_context(patch.object(system_state, "_ma_failures", set()))
        self.stack.enter_context(patch.object(system_state, "_ma_failure_version", 0))
        self.start_connections = len(self.offline.connections)
        self.offline.memory_uris.add(self.ma_uri)
        self.stack.callback(self.offline.memory_uris.remove, self.ma_uri)
        self.stack.enter_context(chdir(self.path))
        self.stack.enter_context(
            patch.dict(os.environ, {"SQLITE_DB_PATH": str(self.disk)})
        )
        self.stack.enter_context(patch.object(database, "_MA_MEM_DB_URI", self.ma_uri))
        self.stack.enter_context(patch.object(database, "_keepalive_ma_conn", None))
        self.stack.enter_context(
            patch.object(
                self.offline.auth, "_kis_env", self.offline.auth._kis_env.model_copy()
            )
        )
        self.stack.enter_context(patch.dict(self.offline.auth._base_headers))
        self.db_token = database.test_db_var.set(str(self.disk))
        self.stack.callback(database.test_db_var.reset, self.db_token)
        self.mem_token = database.test_mem_var.set(None)
        self.stack.callback(database.test_mem_var.reset, self.mem_token)
        try:
            database.init_sqlite_connection()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

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
            self.database.connect_ma_db()
            if table.endswith("_ma")
            else self.database.connect_sqlite()
        )
        try:
            columns = (
                "ticker,date,time,open,high,low,close,volume,amount"
                if table == "minute_ohlcv"
                else "*"
            )
            return [
                tuple(r)
                for r in conn.execute(
                    f"SELECT {columns} FROM {table} ORDER BY 1, 2"
                    + (", 3" if table.startswith("minute") else "")
                )
            ]
        finally:
            conn.close()

    def write(self, sql, records=()):
        conn = self.database.connect_sqlite()
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

    def __exit__(self, *exc):
        try:
            if self.database._keepalive_ma_conn is not None:
                self.database._keepalive_ma_conn.close()
            leaked = [
                c
                for c in self.offline.connections[self.start_connections :]
                if not c.closed
            ]
            for conn in leaked:
                conn.close()
            assert not leaked, f"{len(leaked)} SQLite connections leaked"
        finally:
            self.stack.close()


def load_fixture(name):
    return json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
