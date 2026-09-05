import contextlib
from datetime import datetime, timezone
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load("fetch-usage")
routing = load("choose-builder")
NOW = datetime(2026, 9, 5, 6, tzinfo=timezone.utc)   # before every reset in the fixtures
TOKEN = "sk-ant-oat01-SECRET-TOKEN-VALUE"
CODEX_REPLY = {"id": 2, "result": {"rateLimitsByLimitId": {
    "codex": {"limitId": "codex", "limitName": None,
              "primary": {"usedPercent": 58, "windowDurationMins": 10080, "resetsAt": 1788756651},
              "secondary": None},
    "codex_bengalfox": {"limitId": "codex_bengalfox", "limitName": "GPT-5.3-Codex-Spark",
                        "primary": {"usedPercent": 0, "windowDurationMins": 300, "resetsAt": 1788605079},
                        "secondary": {"usedPercent": 0, "windowDurationMins": 10080, "resetsAt": 1789191879}},
    "codex_sol": {"limitId": "codex_sol", "limitName": "GPT-5.6 Sol",
                  "primary": {"usedPercent": 90, "windowDurationMins": 300, "resetsAt": 1788605079},
                  "secondary": None}}}}
CLAUDE_REPLY = {"limits": [
    {"kind": "session", "percent": 8, "resets_at": "2026-09-05T08:50:00.339001+00:00", "scope": None},
    {"kind": "weekly_all", "percent": 2, "resets_at": "2026-09-05T14:00:00+00:00", "scope": None},
    {"kind": "weekly_scoped", "percent": 3, "resets_at": "2026-09-05T14:00:00+00:00",
     "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None}}]}


def found(name):
    """shutil.which stand-in: both CLIs are on PATH."""
    return f"/fake/bin/{name}"


def codex_run(requests):
    assert '"id":1' in requests and '"id":2' in requests
    return ('{"id":1,"result":{}}\n{"method":"remoteControl/status/changed","params":{}}\n'
            'not json\n' + json.dumps(CODEX_REPLY) + "\n")


def claude_fetch(status=200, body=None):
    calls = []

    def fetch_url(url, headers):
        calls.append((url, headers))
        return status, body if body is not None else json.dumps(CLAUDE_REPLY)
    fetch_url.calls = calls
    return fetch_url


def by_name(rows):
    return {row["name"]: row for row in rows}


class NormalizeTests(unittest.TestCase):
    def document(self, reserve=10):
        return fetch.normalize(fetch.read_codex(codex_run),
                               fetch.read_claude(TOKEN, claude_fetch()), reserve, NOW)

    def test_codex_shared_pool_applies_to_sol_and_astra(self):
        document = self.document()
        for model in ("sol", "astra"):
            row = document[model]
            self.assertTrue(row["complete"])
            self.assertEqual(row["observed_at"], "2026-09-05T06:00:00Z")
            shared = by_name(row["windows"])["Codex codex primary (10080 min)"]
            self.assertEqual(shared["remaining_percent"], 42)   # 100 - 58
            self.assertEqual(shared["reserve_percent"], 10)
            self.assertEqual(shared["resets_at"], fetch.from_epoch(1788756651))
            self.assertTrue(shared["resets_at"].endswith("Z"))

    def test_model_specific_codex_cap_applies_only_when_named(self):
        document = self.document()
        sol = by_name(document["sol"]["windows"])
        astra = by_name(document["astra"]["windows"])
        self.assertEqual(sol["Codex GPT-5.6 Sol primary (300 min)"]["remaining_percent"], 10)
        self.assertNotIn("Codex GPT-5.6 Sol primary (300 min)", astra)
        self.assertFalse(any("Spark" in name for name in list(sol) + list(astra)))

    def test_claude_unscoped_limits_apply_to_both_and_fable_scope_to_fable(self):
        document = self.document()
        opus = by_name(document["opus"]["windows"])
        fable = by_name(document["fable"]["windows"])
        for rows in (opus, fable):
            self.assertEqual(rows["Claude session"]["remaining_percent"], 92)
            self.assertEqual(rows["Claude weekly_all"]["remaining_percent"], 98)
            self.assertEqual(rows["Claude session"]["resets_at"], "2026-09-05T08:50:00Z")
        self.assertEqual(fable["Claude weekly_scoped (Fable)"]["remaining_percent"], 97)
        self.assertNotIn("Claude weekly_scoped (Fable)", opus)
        self.assertTrue(document["opus"]["complete"])

    def test_reserve_is_applied_to_every_window(self):
        document = self.document(reserve=25)
        for row in document.values():
            self.assertTrue(all(w["reserve_percent"] == 25 for w in row["windows"]))

    def test_failed_provider_is_omitted(self):
        document = fetch.normalize(None, fetch.read_claude(TOKEN, claude_fetch()), 10, NOW)
        self.assertEqual(sorted(document), ["fable", "opus"])
        document = fetch.normalize(fetch.read_codex(codex_run), None, 10, NOW)
        self.assertEqual(sorted(document), ["astra", "sol"])

    def test_missing_cli_is_written_as_unavailable(self):
        document = fetch.normalize(None, fetch.read_claude(TOKEN, claude_fetch()), 10, NOW,
                                   missing={"codex": "codex CLI not on PATH"})
        self.assertEqual(sorted(document), ["astra", "fable", "opus", "sol"])
        self.assertEqual(document["sol"], {"available": False, "source": "codex CLI not on PATH"})
        self.assertEqual(document["astra"], document["sol"])
        self.assertEqual(routing.choose("low", document, NOW)["selected_model"], "opus")
        self.assertIsNone(routing.choose("scientific", document, NOW)["selected_model"])

    def test_selector_accepts_the_document(self):
        document = self.document()
        for level in ("low", "high", "scientific", "planner"):
            result = routing.choose(level, document, NOW)
            self.assertTrue(result["comparison_complete"], level)
            self.assertIn(result["selected_model"], routing.POOLS[level])

    def test_token_never_appears_in_output(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = fetch.main(["--reserve", "5"], codex_reader=lambda: fetch.read_codex(codex_run),
                              claude_reader=lambda: fetch.read_claude(TOKEN, claude_fetch()),
                              which=found)
        self.assertEqual(code, 0)
        self.assertNotIn(TOKEN, stdout.getvalue())
        self.assertEqual(json.loads(stdout.getvalue())["sol"]["windows"][0]["reserve_percent"], 5)


class ProviderFailureTests(unittest.TestCase):
    def test_codex_reply_without_limits_fails(self):
        with self.assertRaises(fetch.UsageError):
            fetch.read_codex(lambda requests: '{"id":2,"result":{}}\n')
        with self.assertRaises(fetch.UsageError):
            fetch.read_codex(lambda requests: '{"id":1,"result":{}}\n')

    def test_claude_http_errors_fail(self):
        with self.assertRaisesRegex(fetch.UsageError, "expired"):
            fetch.read_claude(TOKEN, claude_fetch(status=401))
        with self.assertRaisesRegex(fetch.UsageError, "HTTP 500"):
            fetch.read_claude(TOKEN, claude_fetch(status=500))
        with self.assertRaises(fetch.UsageError):
            fetch.read_claude(TOKEN, claude_fetch(body="<html>"))

    def test_claude_request_uses_bearer_token_and_beta_header(self):
        fetch_url = claude_fetch()
        fetch.read_claude(TOKEN, fetch_url)
        url, headers = fetch_url.calls[0]
        self.assertEqual(url, fetch.CLAUDE_USAGE_URL)
        self.assertEqual(headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(headers["anthropic-beta"], "oauth-2025-04-20")

    def run_main(self, codex_ok, claude_ok, which=found, argv=()):
        def fail():
            raise fetch.UsageError("nope")
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = fetch.main(
                list(argv), codex_reader=(lambda: fetch.read_codex(codex_run)) if codex_ok else fail,
                claude_reader=(lambda: fetch.read_claude(TOKEN, claude_fetch())) if claude_ok else fail,
                which=which)
        return code, json.loads(stdout.getvalue()), stderr.getvalue()

    def test_exit_codes(self):
        code, document, stderr = self.run_main(True, False)
        self.assertEqual((code, sorted(document)), (0, ["astra", "sol"]))
        self.assertIn("claude: nope", stderr)
        code, document, stderr = self.run_main(False, False)
        self.assertEqual((code, document), (1, {}))
        self.assertIn("codex: nope", stderr)

    def test_missing_cli_is_known_unavailability(self):
        unavailable = {"available": False}
        code, document, stderr = self.run_main(True, True, which=lambda name: None)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(document), ["astra", "fable", "opus", "sol"])
        for model in ("sol", "astra"):
            self.assertEqual(document[model], dict(unavailable, source="codex CLI not on PATH"))
        for model in ("opus", "fable"):
            self.assertEqual(document[model], dict(unavailable, source="claude CLI not on PATH"))
        self.assertIn("codex: codex CLI not on PATH", stderr)
        self.assertIn("claude: claude CLI not on PATH", stderr)
        for level in ("low", "high", "scientific", "planner"):
            result = routing.choose(level, document, NOW)
            self.assertIsNone(result["selected_model"], level)
            self.assertTrue(all(o["status"] == "unavailable" for o in result["observations"].values()))
        # Only the missing CLI's models are unavailable; the other provider is still read.
        code, document, _ = self.run_main(True, True, which=lambda name: None if name == "codex" else found(name))
        self.assertEqual(code, 0)
        self.assertFalse(document["sol"]["available"])
        self.assertTrue(document["opus"]["available"] and document["opus"]["windows"])

    def test_quota_read_failure_still_omits_the_provider(self):
        code, document, stderr = self.run_main(False, True)
        self.assertEqual((code, sorted(document)), (0, ["fable", "opus"]))
        self.assertIn("codex: nope", stderr)
        self.assertNotIn("not on PATH", stderr)

    def test_choose_runs_the_selector(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = fetch.main(["--choose", "high"], codex_reader=lambda: fetch.read_codex(codex_run),
                              claude_reader=lambda: fetch.read_claude(TOKEN, claude_fetch()),
                              which=found)
        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["level"], "high")
        self.assertTrue(result["comparison_complete"])

    def test_choose_planner_ranks_astra_and_fable(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = fetch.main(["--choose", "planner"], codex_reader=lambda: fetch.read_codex(codex_run),
                              claude_reader=lambda: fetch.read_claude(TOKEN, claude_fetch()),
                              which=found)
        result = json.loads(stdout.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["level"], "planner")
        self.assertEqual(sorted(result["observations"]), ["astra", "fable"])
        self.assertIn(result["selected_model"], ("astra", "fable"))

    def test_unknown_provider_exits_2(self):
        done = subprocess.run([sys.executable, str(SCRIPTS / "fetch-usage.py"), "--providers", "gemini"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        done = subprocess.run([sys.executable, str(SCRIPTS / "fetch-usage.py"), "--choose", "max"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        (self.home / ".claude").mkdir()

    def write_credentials(self, token=TOKEN, expires_at=None):
        oauth = {"accessToken": token}
        if expires_at is not None:
            oauth["expiresAt"] = expires_at
        (self.home / ".claude" / ".credentials.json").write_text(
            json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")

    @staticmethod
    def security(returncode, stdout):
        def run(argv, **kwargs):
            assert argv[:2] == ["security", "find-generic-password"]
            return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="")
        return run

    def test_file_is_used_when_keychain_fails(self):
        self.write_credentials()
        token = fetch.claude_token(self.home, self.security(44, ""), NOW)
        self.assertEqual(token, TOKEN)

    def test_keychain_wins_on_macos(self):
        self.write_credentials(token="file-token")
        blob = json.dumps({"claudeAiOauth": {"accessToken": "keychain-token"}})
        token = fetch.claude_token(self.home, self.security(0, blob + "\n"), NOW)
        expected = "keychain-token" if sys.platform == "darwin" else "file-token"
        self.assertEqual(token, expected)

    def test_missing_login_and_expired_login_fail(self):
        with self.assertRaisesRegex(fetch.UsageError, "not found"):
            fetch.claude_token(self.home, self.security(44, ""), NOW)
        self.write_credentials(expires_at=int((NOW.timestamp() - 60) * 1000))
        with self.assertRaisesRegex(fetch.UsageError, "expired"):
            fetch.claude_token(self.home, self.security(44, ""), NOW)
        self.write_credentials(expires_at=int((NOW.timestamp() + 3600) * 1000))
        self.assertEqual(fetch.claude_token(self.home, self.security(44, ""), NOW), TOKEN)


if __name__ == "__main__":
    unittest.main()
