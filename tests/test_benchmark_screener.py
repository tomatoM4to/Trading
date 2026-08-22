import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_screener import SCENARIOS, BenchmarkStreamError, read_screener_stream
from schemas.screener import ScreenerRequest


class BenchmarkScenarioContractTests(unittest.TestCase):
    def test_scenarios_have_seven_realistic_and_five_heavy_cases(self):
        light = [
            scenario for scenario in SCENARIOS if scenario["name"].startswith("Light ")
        ]
        heavy = [
            scenario for scenario in SCENARIOS if scenario["name"].startswith("Heavy ")
        ]

        self.assertEqual(len(light), 7)
        self.assertEqual(len(heavy), 5)
        self.assertEqual(len(SCENARIOS), 12)

    def test_all_payloads_follow_current_screener_ast_contract(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario["name"]):
                ScreenerRequest.model_validate(scenario["payload"])

    def test_newest_filters_are_covered_by_standalone_scenarios(self):
        standalone_types = {
            scenario["payload"]["filters"][0]["type"]
            for scenario in SCENARIOS
            if len(scenario["payload"]["filters"]) == 1
        }

        self.assertIn("disparity_value", standalone_types)
        self.assertIn("volume_peak_breakout", standalone_types)

    def test_light_ma_windows_are_not_one_or_two_candles(self):
        for scenario in SCENARIOS:
            if not scenario["name"].startswith("Light "):
                continue
            for filter_node in scenario["payload"]["filters"]:
                for key in ("duration", "within"):
                    if key in filter_node["params"]:
                        with self.subTest(scenario=scenario["name"], key=key):
                            self.assertGreaterEqual(filter_node["params"][key], 5)

    def test_heavy_cases_do_not_short_circuit_through_investor_rankings(self):
        investor_filters = {"foreign_net_buy_rank", "inst_net_buy_rank"}

        for scenario in SCENARIOS:
            if not scenario["name"].startswith("Heavy "):
                continue
            types = {node["type"] for node in scenario["payload"]["filters"]}
            with self.subTest(scenario=scenario["name"]):
                self.assertTrue(types.isdisjoint(investor_filters))

    def test_heavy_cases_do_not_reduce_candidates_through_and_chains(self):
        for scenario in SCENARIOS:
            if not scenario["name"].startswith("Heavy "):
                continue
            with self.subTest(scenario=scenario["name"]):
                self.assertNotIn("AND", scenario["payload"]["operations"])

    def test_two_way_and_three_way_or_cases_are_present(self):
        branch_counts = {
            scenario["payload"]["operations"].count("OR") + 1
            for scenario in SCENARIOS
            if "OR" in scenario["payload"]["operations"]
        }

        self.assertIn(2, branch_counts)
        self.assertIn(3, branch_counts)


class BenchmarkStreamTests(unittest.TestCase):
    def test_complete_event_returns_item_count(self):
        lines = [
            b'data: {"type": "start", "filter_id": "f1"}',
            b'data: {"type": "complete", "items": [{"ticker": "A"}, {"ticker": "B"}]}',
        ]

        self.assertEqual(read_screener_stream(lines), 2)

    def test_error_event_fails_the_scenario(self):
        lines = [b'data: {"type": "error", "message": "invalid filter"}']

        with self.assertRaisesRegex(BenchmarkStreamError, "invalid filter"):
            read_screener_stream(lines)

    def test_stream_without_complete_event_fails_the_scenario(self):
        lines = [b'data: {"type": "progress", "remaining": 10}']

        with self.assertRaisesRegex(BenchmarkStreamError, "complete"):
            read_screener_stream(lines)


if __name__ == "__main__":
    unittest.main()
