import importlib.util
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/choose-builder.py"
spec = importlib.util.spec_from_file_location("routing", SCRIPT)
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
        for reviewer in (row(10, reserve=10), row(5, reserve=10)):
            result = self.choose("scientific", astra=row(80), fable=reviewer)
            self.assertEqual(result["selected_model"], "astra")
            self.assertTrue(result["comparison_complete"])

    def test_scientific_reviewer_with_measured_minus_one_is_viable(self):
        # 9 remaining - 10 reserve = -1 must not read as "unavailable".
        result = self.choose("scientific", astra=row(80), fable=row(9, reserve=10))
        self.assertEqual(result["selected_model"], "astra")
        fable = result["observations"]["fable"]
        self.assertEqual((fable["status"], fable["usable_remaining_percent"]), ("measured", -1))
        self.assertTrue(result["comparison_complete"])

    def test_observation_status_is_explicit(self):
        self.assertEqual(routing.observation(None, NOW)[:2], ("unknown", None))
        self.assertEqual(routing.observation({"available": False}, NOW)[:2], ("unavailable", None))
        self.assertEqual(routing.observation(row(0), NOW)[:2], ("exhausted", None))
        self.assertEqual(routing.observation(row(9, reserve=10), NOW)[:2], ("measured", -1))
        # The reason of an unavailable model relays its recorded source.
        unavailable = {"available": False, "source": "codex CLI not on PATH"}
        self.assertEqual(self.choose(sol=unavailable)["observations"]["sol"]["reason"],
                         "codex CLI not on PATH")

    def test_known_exhaustion_beats_unknown_completeness(self):
        exhausted = row(50, 0)
        exhausted["complete"] = False
        result = self.choose(sol=exhausted, opus=row(10))
        self.assertEqual(result["selected_model"], "opus")
        self.assertEqual(result["observations"]["sol"]["status"], "exhausted")
        self.assertIsNone(self.choose(sol=exhausted, opus={"available": False})["selected_model"])
        # A zero window that has already reset is not known exhaustion.
        reset = row(0)
        reset["windows"][0]["resets_at"] = (NOW - timedelta(minutes=1)).isoformat()
        self.assertEqual(self.choose(sol=reset)["selected_model"], "sol")
        # Scientific: an exhausted incomplete observation cannot review either.
        self.assertIsNone(self.choose("scientific", astra=row(90), fable=exhausted)
                          ["selected_model"])

    def test_planner_picks_measured_headroom_in_astra_fable_pool(self):
        result = self.choose("planner", astra=row(40), fable=row(70, 55))
        self.assertEqual((result["selected_model"], result["effort"]), ("fable", "high"))
        self.assertTrue(result["comparison_complete"])
        result = self.choose("planner", astra=row(60), fable=row(30))
        self.assertEqual((result["selected_model"], result["effort"]), ("astra", "medium"))

    def test_planner_unknown_defaults_to_astra(self):
        result = self.choose("planner")
        self.assertEqual(result["selected_model"], "astra")
        self.assertFalse(result["comparison_complete"])
        # A known viable candidate beats the unknown one.
        result = self.choose("planner", fable=row(20))
        self.assertEqual(result["selected_model"], "fable")
        self.assertFalse(result["comparison_complete"])

    def test_planner_excludes_unavailable_and_exhausted(self):
        result = self.choose("planner", astra={"available": False}, fable=row(10))
        self.assertEqual(result["selected_model"], "fable")
        self.assertEqual(result["observations"]["astra"]["status"], "unavailable")
        self.assertEqual(self.choose("planner", astra=row(0), fable=row(10))["selected_model"], "fable")
        self.assertIsNone(self.choose("planner", astra={"available": False}, fable=row(0))
                          ["selected_model"])
        # Unlike scientific, the planner does not require the other model to be viable.
        self.assertEqual(self.choose("planner", astra=row(50), fable={"available": False})
                         ["selected_model"], "astra")

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


class CliTests(unittest.TestCase):
    """Exit codes as usage-format.md documents: 0 selected, 1 nothing viable, 2 bad input."""

    def run_cli(self, level, data):
        with tempfile.TemporaryDirectory() as temp:
            usage = Path(temp) / "usage.json"
            usage.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), level, str(usage)],
                                  capture_output=True, text=True)

    def fresh(self, *remaining, **extra):
        value = row(*remaining, **extra)
        value["observed_at"] = datetime.now(timezone.utc).isoformat()
        return value

    def test_exit_0_when_selected(self):
        done = self.run_cli("low", {"sol": self.fresh(60), "opus": self.fresh(40)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["selected_model"], "sol")
        done = self.run_cli("high", {})
        self.assertEqual(done.returncode, 0)
        self.assertFalse(json.loads(done.stdout)["comparison_complete"])

    def test_exit_1_when_nothing_viable(self):
        done = self.run_cli("scientific", {"astra": {"available": False}, "fable": self.fresh(0)})
        self.assertEqual(done.returncode, 1)
        self.assertIsNone(json.loads(done.stdout)["selected_model"])

    def test_exit_2_on_invalid_input(self):
        for data in ("{not json", {"sol": self.fresh(150)}, {"sol": {"available": "yes"}}, []):
            with self.subTest(data=data):
                self.assertEqual(self.run_cli("low", data).returncode, 2)
        self.assertEqual(self.run_cli("max", {}).returncode, 2)


if __name__ == "__main__":
    unittest.main()
