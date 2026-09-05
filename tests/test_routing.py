import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "routing", Path(__file__).resolve().parents[1] / "scripts/choose-builder.py")
routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routing)
NOW = datetime(2026, 9, 5, 10, tzinfo=timezone.utc)


def row(*remaining, reserve=0):
    return {"available": True, "source": "test quota surface",
            "observed_at": NOW.isoformat(), "complete": True,
            "windows": [{"name": str(i), "remaining_percent": value,
                         "reserve_percent": reserve}
                        for i, value in enumerate(remaining)]}


class RoutingTests(unittest.TestCase):
    def choose(self, level="low", **data):
        return routing.choose(level, data, NOW)

    def test_uses_bottleneck_not_best_window(self):
        result = self.choose(sol=row(95, 20), opus=row(60, 50))
        self.assertEqual(result["selected_model"], "opus")
        self.assertEqual(result["effort"], "xhigh")

    def test_subtracts_reserve(self):
        self.assertEqual(self.choose(sol=row(80, reserve=40), opus=row(60))
                         ["selected_model"], "opus")

    def test_shared_cap_applies_to_scientific(self):
        result = self.choose("scientific", astra=row(75, 15), fable=row(60, 45))
        self.assertEqual(result["selected_model"], "fable")
        self.assertEqual(result["effort"], "high")

    def test_scientific_astra_is_medium(self):
        self.assertEqual(self.choose("scientific", astra=row(80), fable=row(20))
                         ["effort"], "medium")

    def test_unknown_is_disclosed_and_known_viable_wins(self):
        result = self.choose(opus=row(30))
        self.assertEqual(result["selected_model"], "opus")
        self.assertFalse(result["comparison_complete"])

    def test_both_unknown_use_stable_fallback(self):
        self.assertEqual(self.choose()["selected_model"], "sol")
        self.assertFalse(self.choose()["comparison_complete"])

    def test_stale_incomplete_future_and_reset_are_unknown(self):
        for kind in ("stale", "incomplete", "future", "reset"):
            with self.subTest(kind=kind):
                value = row(99)
                if kind == "stale":
                    value["observed_at"] = (NOW - timedelta(minutes=6)).isoformat()
                elif kind == "incomplete":
                    value["complete"] = False
                elif kind == "future":
                    value["observed_at"] = (NOW + timedelta(minutes=6)).isoformat()
                else:
                    value["windows"][0]["resets_at"] = NOW.isoformat()
                result = self.choose(sol=value, opus=row(10))
                self.assertEqual(result["selected_model"], "opus")
                self.assertFalse(result["comparison_complete"])

    def test_unavailable_and_exhausted_are_excluded(self):
        result = self.choose(sol={"available": False}, opus=row(10, reserve=10))
        self.assertIsNone(result["selected_model"])

    def test_scientific_requires_other_reviewer(self):
        for value in ({"available": False}, row(0)):
            self.assertIsNone(self.choose("scientific", astra=row(90), fable=value)
                              ["selected_model"])

    def test_scientific_can_spend_reserved_capacity_on_review(self):
        result = self.choose("scientific", astra=row(80), fable=row(10, reserve=10))
        self.assertEqual(result["selected_model"], "astra")

    def test_tie_is_stable(self):
        self.assertEqual(self.choose("high", sol=row(50), opus=row(50))
                         ["selected_model"], "sol")

    def test_invalid_percentages_fail(self):
        for value in (-1, 101, float("nan"), True, "50"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.choose(sol=row(value), opus=row(30))

    def test_missing_reserve_fails(self):
        value = row(50)
        del value["windows"][0]["reserve_percent"]
        with self.assertRaises(KeyError):
            self.choose(sol=value)


if __name__ == "__main__":
    unittest.main()
