import itertools
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from tests.data import daily_series, ma_reference, minute_series
from tests.transport import FakeTransport, response


def decode_events(text):
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


pytestmark = pytest.mark.stage4


@pytest.mark.parametrize("cumulative", [1122, None])
def test_screener_amount_is_latest_session_cumulative_even_with_missing_minutes(
    sandbox, cumulative
):
    from services.screener_service import ScreenerEngine

    sandbox.stock("snapshot")
    sandbox.write(
        "INSERT INTO minute_ohlcv (ticker,date,time,open,high,low,close,volume,amount,cumulative_amount) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [("snapshot", 20261109, 153000, 100, 123, 90, 120, 4, None, cumulative)],
    )
    item = ScreenerEngine().get_ticker_names({"snapshot": {}})[0]
    assert item["amount"] == cumulative
    assert item["amount_asof"] == "2026-11-09 15:30:00"


def test_admin_test_routes_are_removed_but_live_routes_remain():
    from main import app

    paths = app.openapi()["paths"]
    assert not any(path.startswith("/admin/test/") for path in paths)
    assert "/admin/live/global-status" in paths
    assert "/admin/live/ticker-status/{ticker}" in paths


@pytest.fixture(autouse=True)
async def market_data(sandbox):
    from core.bootstrap import rebuild_ma_database

    market_data = {}
    for ticker, count in [
        ("A", 240),
        ("B", 240),
        ("C", 240),
        ("D", 240),
        ("E", 4),
        ("H", 240),
    ]:
        sandbox.stock(ticker, halted=int(ticker == "H"))
        for minute in (False, True):
            rows = (
                minute_series(count, ticker) if minute else daily_series(count, ticker)
            )
            changed = []
            for i, row in enumerate(rows):
                close = {
                    "A": 100 + i,
                    "B": 500 - i,
                    "C": 200,
                    "D": 100 + i * 29 % 79,
                    "E": 100 + i,
                    "H": 100 + i,
                }[ticker]
                if not minute:
                    date = int(
                        (
                            datetime(2026, 11, 12) - timedelta(days=count - 1 - i)
                        ).strftime("%Y%m%d")
                    )
                    row = (ticker, date, *row[2:])
                changed.append(
                    (
                        *row[: 3 if minute else 2],
                        close,
                        close + 3,
                        close - 3,
                        close,
                        row[-2],
                        close * row[-2],
                    )
                )
            market_data[ticker, minute] = changed
            table, placeholders = (
                ("minute_ohlcv", "?,?,?,?,?,?,?,?,?")
                if minute
                else ("daily_ohlcv", "?,?,?,?,?,?,?,?")
            )
            columns = (
                "ticker,date,time,open,high,low,close,volume,amount"
                if minute
                else "ticker,date,open,high,low,close,volume,amount"
            )
            sandbox.write(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", changed
            )
    await rebuild_ma_database()
    return market_data


def reference(market_data, kind, params, minute=False):
    result = {}
    for ticker in ("A", "B", "C", "D", "E"):
        raw = market_data[ticker, minute]
        ma = ma_reference(raw, minute=minute)
        pairs = [(r[-6], r[-4]) for r in ma]
        differences = [
            None
            if a is None or b is None or min(a, b) <= 0
            else (max(a, b) - min(a, b)) / min(a, b) * 100
            for a, b in pairs
        ]
        value = None
        if kind == "ma_alignment":
            window = pairs[-params["duration"] :]
            if len(window) == params["duration"] and all(
                (a is not None and b is not None and (a > b) for a, b in window)
            ):
                value = sum(differences[-params["duration"] :]) / params["duration"]
        elif kind == "ma_convergence_consolidation":
            window = differences[-params["duration"] :]
            if len(window) == params["duration"] and all(
                v is not None and v <= params["threshold"] for v in window
            ):
                value = sum(window) / len(window)
        elif kind == "ma_convergence_point":
            matches = [
                v
                for v in differences[-params["within"] :]
                if v is not None and v <= params["threshold"]
            ]
            if matches:
                value = min(matches)
        elif kind == "ma_cross":
            candidates = []
            for index in range(max(1, len(pairs) - params["within"]), len(pairs)):
                prev_s, prev_l = pairs[index - 1]
                short, long = pairs[index]
                if any(v is None for v in (prev_s, prev_l, short, long)):
                    continue
                if (
                    params["direction"] == "golden"
                    and prev_s <= prev_l
                    and (short > long)
                ):
                    candidates.append((short - long) / long * 100)
                if (
                    params["direction"] == "dead"
                    and prev_s >= prev_l
                    and (short < long)
                ):
                    candidates.append((long - short) / short * 100)
            if candidates:
                value = max(candidates)
        elif kind == "disparity_value":
            avg = pairs[-1][0]
            if avg:
                disparity = raw[-1][6 if minute else 5] / avg * 100
                if (
                    disparity >= params["threshold"]
                    if params["direction"] == "above"
                    else disparity <= params["threshold"]
                ):
                    value = disparity
        elif kind == "volume_peak_breakout":
            count = {"1M": 30, "3M": 60, "2H": 120, "4H": 240}[params["lookback"]]
            history = raw[-count - 1 : -1]
            if history:
                peak = max(history, key=lambda r: (r[-2], r[1 : 3 if minute else 2]))
                high, close = (peak[4 if minute else 3], raw[-1][6 if minute else 5])
                if close > high:
                    value = (close - high) / high * 100
        if value is not None:
            result[ticker] = {"f": round(value, 4)}
    return result


@pytest.mark.parametrize("lookback", ("1M", "3M", "2H", "4H"))
async def test_volume_peak_breakout_matches_arithmetic_reference(
    market_data, engine, lookback
):
    from schemas.screener import ScreenerRequest

    params = {"lookback": lookback}
    request = ScreenerRequest(
        filters=[{"id": "f", "type": "volume_peak_breakout", "params": params}]
    )
    assert await engine.run_pipeline(request) == reference(
        market_data, "volume_peak_breakout", params, "H" in lookback
    )


@pytest.mark.parametrize("minute", [False, True], ids=["daily", "minute"])
@pytest.mark.parametrize(
    "kind,values",
    [
        ("ma_alignment", {"duration": 1}),
        ("ma_alignment", {"duration": 3}),
        ("ma_alignment", {"duration": 300}),
        ("ma_convergence_consolidation", {"duration": 3, "threshold": 0}),
        ("ma_convergence_consolidation", {"duration": 5, "threshold": 5}),
        ("ma_convergence_point", {"within": 12, "threshold": 2}),
        ("ma_cross", {"within": 30, "direction": "golden"}),
        ("ma_cross", {"within": 30, "direction": "dead"}),
        ("disparity_value", {"threshold": 100, "direction": "above"}),
        ("disparity_value", {"threshold": 100, "direction": "below"}),
    ],
    ids=[
        "alignment-1",
        "alignment-3",
        "alignment-300",
        "consolidation-0",
        "consolidation-5",
        "convergence-point",
        "golden-cross",
        "dead-cross",
        "disparity-above",
        "disparity-below",
    ],
)
async def test_each_local_filter_matches_arithmetic_reference(
    market_data, engine, minute, kind, values
):
    from schemas.screener import ScreenerRequest

    prefix = "ma" if minute else "ma_daily_"
    params = {**values}
    if kind == "ma_cross":
        params.update(short_line=f"{prefix}5", long_line=f"{prefix}20")
    elif kind == "disparity_value":
        params["line"] = f"{prefix}5"
    else:
        params["lines"] = [f"{prefix}5", f"{prefix}20"]
    actual = await engine.run_pipeline(
        ScreenerRequest(filters=[{"id": "f", "type": kind, "params": params}])
    )
    assert actual == reference(market_data, kind, values, minute)


@pytest.mark.parametrize(
    "operations",
    list(itertools.product(("AND", "OR"), repeat=2)),
    ids=["and-and", "and-or", "or-and", "or-or"],
)
async def test_all_and_or_combinations_match_set_reference(
    market_data, engine, operations
):
    from schemas.screener import ScreenerRequest

    definitions = [
        ("ma_alignment", {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 3}),
        (
            "ma_convergence_point",
            {"lines": ["ma_daily_5", "ma_daily_20"], "within": 12, "threshold": 2},
        ),
        (
            "ma_cross",
            {
                "short_line": "ma_daily_5",
                "long_line": "ma_daily_20",
                "within": 30,
                "direction": "dead",
            },
        ),
    ]
    refs = [reference(market_data, kind, params) for kind, params in definitions]
    request = ScreenerRequest(
        filters=[
            {"id": str(i), "type": kind, "params": params}
            for i, (kind, params) in enumerate(definitions)
        ],
        operations=list(operations),
    )
    expected = {}
    for ticker in ("A", "B", "C", "D", "E"):
        groups = [[0]]
        for i, operation in enumerate(operations, 1):
            if operation == "OR":
                groups.append([i])
            else:
                groups[-1].append(i)
        passing = [g for g in groups if all(ticker in refs[i] for i in g)]
        if passing:
            expected[ticker] = {
                str(i): refs[i][ticker]["f"] for group in passing for i in group
            }
    assert await engine.run_pipeline(request) == expected
    with patch.object(engine, "_estimate_cost", return_value=0):
        assert await engine.run_pipeline(request) == expected


@pytest.mark.parametrize("rank_type", ["foreign_net_buy_rank", "inst_net_buy_rank"])
@pytest.mark.parametrize("blocked", ["halted", "admin"])
async def test_cost_reordering_preserves_eligibility_with_investor_rank(
    engine, sandbox, rank_type, blocked
):
    from schemas.screener import ScreenerRequest

    sandbox.write(
        "UPDATE stock_codes SET is_halted=?, is_admin_issue=? WHERE ticker='H'",
        [(int(blocked == "halted"), int(blocked == "admin"))],
    )
    request = ScreenerRequest(
        filters=[
            {
                "id": "ma",
                "type": "ma_alignment",
                "params": {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 1},
            },
            {"id": "rank", "type": rank_type, "params": {"limit": 30}},
        ],
        operations=["AND"],
    )
    ranked = [{"mksc_shrn_iscd": "H"}, {"mksc_shrn_iscd": "A"}]
    with FakeTransport([response(ranked, output="output")] * 2):
        optimized = await engine.run_pipeline(request)
        with patch.object(engine, "_estimate_cost", return_value=0):
            original = await engine.run_pipeline(request)
    assert set(original) == {"A"}
    assert optimized == original


@pytest.mark.parametrize(
    "status,rt_cd",
    [(200, "1"), (503, "0"), (200, "0")],
    ids=["broker-error", "http-error", "malformed-output"],
)
async def test_sse_broker_error_is_not_successful_empty_result(status, rt_cd):
    from httpx import ASGITransport, AsyncClient
    from main import app

    payload = {
        "filters": [
            {"id": "rank", "type": "foreign_net_buy_rank", "params": {"limit": 1}}
        ],
        "operations": [],
    }
    with FakeTransport([response(status=status, rt_cd=rt_cd)]):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            result = await client.post("/api/screener/run", json=payload)
    events = decode_events(result.text)
    assert result.status_code == 200
    assert events[-1]["type"] == "error"
    assert not any(e["type"] == "complete" for e in events)


@pytest.mark.parametrize(
    "rows",
    [
        [{}],
        [{"mksc_shrn_iscd": ""}],
        [{"mksc_shrn_iscd": 123}],
        [None],
        [{"mksc_shrn_iscd": "A"}, {}],
    ],
)
async def test_sse_malformed_rank_rows_cannot_become_successful_empty_result(rows):
    from httpx import ASGITransport, AsyncClient
    from main import app

    payload = {
        "filters": [
            {"id": "rank", "type": "foreign_net_buy_rank", "params": {"limit": 3}}
        ]
    }
    with FakeTransport([response(rows, output="output")]):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            result = await client.post("/api/screener/run", json=payload)
    events = decode_events(result.text)
    assert [
        event["type"] for event in events if event["type"] in {"complete", "error"}
    ] == ["error"]


@pytest.mark.parametrize("rank_type", ["foreign_net_buy_rank", "inst_net_buy_rank"])
async def test_sse_empty_investor_rank_is_successful_completion(rank_type):
    from httpx import ASGITransport, AsyncClient
    from main import app

    payload = {
        "filters": [
            {"id": "rank", "type": "foreign_net_buy_rank", "params": {"limit": 1}}
        ]
    }
    payload["filters"][0]["type"] = rank_type
    with FakeTransport([response([], output="output")]):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://fixture"
        ) as client:
            result = await client.post("/api/screener/run", json=payload)
    events = decode_events(result.text)
    assert [event for event in events if event["type"] in {"complete", "error"}] == [
        {"type": "complete", "items": []}
    ]


@pytest.mark.parametrize("rank_type", ["foreign_net_buy_rank", "inst_net_buy_rank"])
async def test_standalone_rank_excludes_ineligible_tickers_without_changing_rank(
    engine, rank_type
):
    from schemas.screener import ScreenerRequest

    ranked = [{"mksc_shrn_iscd": ticker} for ticker in ("unknown", "H", "A")]
    request = ScreenerRequest(
        filters=[{"id": "rank", "type": rank_type, "params": {"limit": 3}}]
    )
    with FakeTransport([response(ranked, output="output")]):
        assert await engine.run_pipeline(request) == {"A": {"rank": 3.0}}


@pytest.mark.parametrize(
    "kind,params,terminal",
    [
        (
            "ma_alignment",
            {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 3},
            "complete",
        ),
        ("unsupported", {}, "error"),
    ],
    ids=["success", "unsupported-filter"],
)
async def test_sse_success_error_and_single_terminal_event(
    market_data, kind, params, terminal
):
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    result = client.post(
        "/api/screener/run",
        json={
            "filters": [{"id": "f", "type": kind, "params": params}],
            "operations": [],
        },
    )
    events = decode_events(result.text)
    assert "text/event-stream" in result.headers["content-type"]
    assert [e["type"] for e in events if e["type"] in {"complete", "error"}] == [
        terminal
    ]
    if terminal == "complete":
        assert {
            i["ticker"]: i["filter_values"] for i in events[-1]["items"]
        } == reference(market_data, kind, params)


@pytest.mark.parametrize("minute", (False, True), ids=["daily", "minute"])
async def test_chart_all_ohlcv_and_ma_values_match_source(market_data, minute):
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    result = client.get(
        f"/market/chart/A?days=4&type={('minute' if minute else 'daily')}"
    )
    assert result.status_code == 200
    raw = market_data["A", minute]
    chart = result.json()["data"]
    assert len(chart) == len(raw)
    closes = []
    for original, point in zip(raw, chart, strict=True):
        offset = 3 if minute else 2
        assert [point[k] for k in ("open", "high", "low", "close", "volume")] == list(
            original[offset : offset + 5]
        )
        closes.append(original[6 if minute else 5])
        for period in (5, 10, 20, 60, 120, 200):
            value = point[f"ma{period}" if minute else f"ma_daily_{period}"]
            if len(closes) < period:
                assert value is None
            else:
                assert value == pytest.approx(
                    sum(closes[-period:]) / period, rel=0, abs=5e-08
                )
        time = original[2] if minute else 153000
        assert (
            point["time"]
            == f"{original[1] // 10000:04}-{original[1] // 100 % 100:02}-{original[1] % 100:02} {time // 10000:02}:{time // 100 % 100:02}:{time % 100:02}"
        )
        if minute:
            assert point["ma1"] == original[6]
            history = [r[5] for r in market_data["A", False] if r[1] <= original[1]]
            assert point["ma_daily_1"] == history[-1]
            for period in (5, 10, 20, 60, 120, 200):
                value = point[f"ma_daily_{period}"]
                if len(history) < period:
                    assert value is None
                else:
                    assert value == pytest.approx(
                        sum(history[-period:]) / period, rel=0, abs=5e-08
                    )


async def test_top_volume_nonempty_database_preserves_public_response(market_data):
    from fastapi.testclient import TestClient
    from main import app

    result = TestClient(app, raise_server_exceptions=False).get(
        "/market/screener/top-volume"
    )
    assert result.status_code == 200
    assert result.json()["date"] == str(market_data["A", False][-1][1])
    expected = [
        r
        for (ticker, minute), rows in market_data.items()
        if not minute
        for r in rows
        if r[1] == market_data["A", False][-1][1]
    ]
    assert {i["ticker"]: i["volume"] for i in result.json()["items"]} == {
        r[0]: r[-2] for r in expected
    }


@pytest.fixture
def engine():
    from services.screener_service import ScreenerEngine

    return ScreenerEngine()
