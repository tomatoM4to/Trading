import itertools
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from tests.data import daily_series, ma_reference, minute_series
from tests.support import DatabaseCase
from tests.transport import FakeTransport, response


def decode_events(text):
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


class ScreenerContracts(DatabaseCase):
    async def asyncSetUp(self):
        from core.bootstrap import rebuild_ma_database
        from services.screener_service import ScreenerEngine

        self.engine = ScreenerEngine()
        self.source = {}
        for ticker, count in [
            ("A", 240),
            ("B", 240),
            ("C", 240),
            ("D", 240),
            ("E", 4),
            ("H", 240),
        ]:
            self.box.stock(ticker, halted=int(ticker == "H"))
            for minute in (False, True):
                rows = (
                    minute_series(count, ticker)
                    if minute
                    else daily_series(count, ticker)
                )
                changed = []
                for i, row in enumerate(rows):
                    close = {
                        "A": 100 + i,
                        "B": 500 - i,
                        "C": 200,
                        "D": 100 + (i * 29) % 79,
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
                self.source[ticker, minute] = changed
                table, placeholders = (
                    ("minute_ohlcv", "?,?,?,?,?,?,?,?,?")
                    if minute
                    else ("daily_ohlcv", "?,?,?,?,?,?,?,?")
                )
                self.box.write(f"INSERT INTO {table} VALUES ({placeholders})", changed)
        await rebuild_ma_database()

    def reference(self, kind, params, minute=False):
        result = {}
        for ticker in ("A", "B", "C", "D", "E"):
            raw = self.source[ticker, minute]
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
                    a is not None and b is not None and a > b for a, b in window
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
                        and short > long
                    ):
                        candidates.append((short - long) / long * 100)
                    if (
                        params["direction"] == "dead"
                        and prev_s >= prev_l
                        and short < long
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
                    peak = max(
                        history, key=lambda r: (r[-2], r[1 : 3 if minute else 2])
                    )
                    high, close = peak[4 if minute else 3], raw[-1][6 if minute else 5]
                    if close > high:
                        value = (close - high) / high * 100
            if value is not None:
                result[ticker] = {"f": round(value, 4)}
        return result

    async def test_each_local_filter_matches_arithmetic_reference(self):
        cases = [
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
        ]
        for minute, (kind, values) in itertools.product((False, True), cases):
            prefix = "ma" if minute else "ma_daily_"
            params = {**values}
            if kind == "ma_cross":
                params.update(short_line=f"{prefix}5", long_line=f"{prefix}20")
            elif kind == "disparity_value":
                params["line"] = f"{prefix}5"
            else:
                params["lines"] = [f"{prefix}5", f"{prefix}20"]
            with self.subTest(kind=kind, minute=minute, values=values):
                actual = await self.engine.filter_handlers[kind]("f", params)
                self.assertEqual(actual, self.reference(kind, values, minute))
        for lookback in ("1M", "3M", "2H", "4H"):
            with self.subTest(lookback=lookback):
                params = {"lookback": lookback}
                self.assertEqual(
                    await self.engine._handle_volume_peak_breakout("f", params),
                    self.reference("volume_peak_breakout", params, "H" in lookback),
                )

    async def test_all_and_or_combinations_match_set_reference(self):
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
        refs = [self.reference(kind, params) for kind, params in definitions]
        for operations in itertools.product(("AND", "OR"), repeat=2):
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
            with self.subTest(operations=operations):
                self.assertEqual(await self.engine.run_pipeline(request), expected)
                with patch.object(self.engine, "_estimate_cost", return_value=0):
                    self.assertEqual(await self.engine.run_pipeline(request), expected)

    async def test_cost_reordering_preserves_eligibility_with_investor_rank(self):
        from schemas.screener import ScreenerRequest

        request = ScreenerRequest(
            filters=[
                {
                    "id": "ma",
                    "type": "ma_alignment",
                    "params": {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 1},
                },
                {"id": "rank", "type": "foreign_net_buy_rank", "params": {"limit": 30}},
            ],
            operations=["AND"],
        )
        ranked = [{"mksc_shrn_iscd": "H"}, {"mksc_shrn_iscd": "A"}]
        with FakeTransport([response(ranked, output="output")] * 2):
            optimized = await self.engine.run_pipeline(request)
            with patch.object(self.engine, "_estimate_cost", return_value=0):
                original = await self.engine.run_pipeline(request)
        self.assertEqual(set(original), {"A"})
        self.assertEqual(optimized, original)

    async def test_sse_broker_error_is_not_successful_empty_result(self):
        from fastapi.testclient import TestClient
        from main import app

        payload = {
            "filters": [
                {"id": "rank", "type": "foreign_net_buy_rank", "params": {"limit": 1}}
            ],
            "operations": [],
        }
        with FakeTransport([response(rt_cd="1")]):
            result = TestClient(app).post("/api/screener/run", json=payload)
        events = decode_events(result.text)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(events[-1]["type"], "error")
        self.assertFalse(any(e["type"] == "complete" for e in events))

    async def test_sse_success_error_and_single_terminal_event(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        for kind, params, terminal in [
            (
                "ma_alignment",
                {"lines": ["ma_daily_5", "ma_daily_20"], "duration": 3},
                "complete",
            ),
            ("unsupported", {}, "error"),
        ]:
            result = client.post(
                "/api/screener/run",
                json={
                    "filters": [{"id": "f", "type": kind, "params": params}],
                    "operations": [],
                },
            )
            events = decode_events(result.text)
            self.assertIn("text/event-stream", result.headers["content-type"])
            self.assertEqual(
                [e["type"] for e in events if e["type"] in {"complete", "error"}],
                [terminal],
            )
            if terminal == "complete":
                self.assertEqual(
                    {i["ticker"]: i["filter_values"] for i in events[-1]["items"]},
                    self.reference(kind, params),
                )

    async def test_chart_all_ohlcv_and_ma_values_match_source(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        for minute in (False, True):
            result = client.get(
                f"/market/chart/A?days=4&type={'minute' if minute else 'daily'}"
            )
            self.assertEqual(result.status_code, 200)
            raw = self.source["A", minute]
            chart = result.json()["data"]
            self.assertEqual(len(chart), len(raw))
            closes = []
            for original, point in zip(raw, chart, strict=True):
                offset = 3 if minute else 2
                self.assertEqual(
                    [point[k] for k in ("open", "high", "low", "close", "volume")],
                    list(original[offset : offset + 5]),
                )
                closes.append(original[6 if minute else 5])
                for period in (5, 10, 20, 60, 120, 200):
                    value = point[f"ma{period}" if minute else f"ma_daily_{period}"]
                    if len(closes) < period:
                        self.assertIsNone(value)
                    else:
                        self.assertAlmostEqual(value, sum(closes[-period:]) / period)
                time = original[2] if minute else 153000
                self.assertEqual(
                    point["time"],
                    f"{original[1] // 10000:04}-{original[1] // 100 % 100:02}-{original[1] % 100:02} {time // 10000:02}:{time // 100 % 100:02}:{time % 100:02}",
                )
                if minute:
                    self.assertEqual(point["ma1"], original[6])
                    history = [
                        r[5] for r in self.source["A", False] if r[1] <= original[1]
                    ]
                    self.assertEqual(point["ma_daily_1"], history[-1])
                    for period in (5, 10, 20, 60, 120, 200):
                        value = point[f"ma_daily_{period}"]
                        if len(history) < period:
                            self.assertIsNone(value)
                        else:
                            self.assertAlmostEqual(
                                value, sum(history[-period:]) / period
                            )

    async def test_top_volume_nonempty_database_preserves_public_response(self):
        from fastapi.testclient import TestClient
        from main import app

        result = TestClient(app, raise_server_exceptions=False).get(
            "/market/screener/top-volume"
        )
        self.assertEqual(result.status_code, 200)
        expected = [
            r
            for (ticker, minute), rows in self.source.items()
            if not minute
            for r in rows
            if r[1] == self.source["A", False][-1][1]
        ]
        self.assertEqual(
            {i["ticker"]: i["volume"] for i in result.json()["items"]},
            {r[0]: r[-2] for r in expected},
        )
