#!/usr/bin/env python3
"""Read Codex and Claude quota from each CLI's own usage endpoint into usage.json.

Codex: `codex app-server` (JSON-RPC on stdio), method account/rateLimits/read.
Claude: the CLI's stored login calls GET https://api.anthropic.com/api/oauth/usage,
the same endpoint the /usage screen uses. The token is used only for that call
and is never printed or written anywhere.

A CLI that is not on PATH is known unavailability: its models are written as
{"available": false, "source": "<cli> CLI not on PATH"} so the selector excludes
them. Any other failure (timeout, no login, HTTP error, bad JSON) is unknown
usage: the provider is omitted and the reason goes to stderr.
"""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

CODEX_MODELS = ("sol", "astra")
CLAUDE_MODELS = ("opus", "fable")
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CODEX_REQUESTS = (
    '{"jsonrpc":"2.0","id":1,"method":"initialize",'
    '"params":{"clientInfo":{"name":"useful-skills","version":"0.1"}}}\n'
    '{"jsonrpc":"2.0","id":2,"method":"account/rateLimits/read","params":{}}\n')
TIMEOUT = 20


class UsageError(Exception):
    """A provider could not be read; the message is the one-line stderr reason."""


def iso(moment):
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def from_epoch(seconds):
    return iso(datetime.fromtimestamp(seconds, tz=timezone.utc))


def from_iso(text):
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return iso(parsed)


def window(name, used, reserve, resets_at=None):
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        raise UsageError(f"{name}: used percent is not a number")
    row = {"name": name, "remaining_percent": max(0, min(100, 100 - used)),
           "reserve_percent": reserve}
    if resets_at:
        row["resets_at"] = resets_at
    return row


# --- Codex -----------------------------------------------------------------

def run_codex_app_server(requests, timeout=TIMEOUT):
    """Send the requests to `codex app-server`; return its stdout up to the id-2 reply."""
    exe = shutil.which("codex")
    if not exe:
        raise UsageError("codex CLI not found on PATH")
    proc = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    lines = queue.Queue()

    def pump():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=pump, daemon=True).start()
    collected = []
    try:
        proc.stdin.write(requests)
        proc.stdin.flush()
        # The server exits as soon as stdin closes, so keep it open until the
        # reply arrives; unrelated notification lines are collected and ignored.
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        while True:
            remaining = deadline - datetime.now(timezone.utc).timestamp()
            if remaining <= 0:
                raise UsageError("codex app-server timed out")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                raise UsageError("codex app-server timed out")
            if line is None:
                raise UsageError("codex app-server exited before answering")
            collected.append(line)
            try:
                if json.loads(line).get("id") == 2:
                    break
            except (ValueError, AttributeError):
                continue
    except (OSError, ValueError) as error:
        raise UsageError(f"codex app-server failed: {error}")
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
    return "".join(collected)


def read_codex(run=run_codex_app_server):
    """Return {"windows": {model: [...]}, "complete": bool} from the shared Codex pool."""
    output = run(CODEX_REQUESTS)
    reply = None
    for line in output.splitlines():
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("id") == 2:
            reply = candidate
    if reply is None:
        raise UsageError("codex app-server gave no rateLimits reply")
    if "error" in reply:
        raise UsageError(f"codex rateLimits error: {reply['error'].get('message', reply['error'])}")
    limits = (reply.get("result") or {}).get("rateLimitsByLimitId")
    if not isinstance(limits, dict):
        raise UsageError("codex reply has no rateLimitsByLimitId (not logged in?)")
    return {"windows": limits, "complete": "codex" in limits}


def codex_windows(limits, reserve):
    """Map rateLimitsByLimitId onto Sol and Astra window lists."""
    result = {model: [] for model in CODEX_MODELS}
    for limit_id, limit in limits.items():
        label = limit.get("limitName") or limit_id
        if limit_id == "codex":
            targets = CODEX_MODELS   # the shared pool for every Codex model
        else:
            targets = tuple(m for m in CODEX_MODELS if m in str(limit.get("limitName") or "").lower())
        for kind in ("primary", "secondary"):
            part = limit.get(kind)
            if not isinstance(part, dict):
                continue
            resets = part.get("resetsAt")
            row = window(f"Codex {label} {kind} ({part.get('windowDurationMins')} min)",
                         part.get("usedPercent"), reserve,
                         from_epoch(resets) if isinstance(resets, (int, float)) else None)
            for model in targets:
                result[model].append(row)
    return result


# --- Claude ----------------------------------------------------------------

def claude_token(home=None, security=None, now=None):
    """The CLI's stored OAuth access token: macOS keychain first, else the credentials file."""
    home = Path(home) if home else Path.home()
    now = now or datetime.now(timezone.utc)
    blob = None
    if sys.platform == "darwin":
        try:
            done = (security or subprocess.run)(
                ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                capture_output=True, text=True, timeout=TIMEOUT)
            if done.returncode == 0 and done.stdout.strip():
                blob = done.stdout
        except (OSError, subprocess.SubprocessError):
            blob = None
    if blob is None:
        try:
            blob = (home / ".claude" / ".credentials.json").read_text(encoding="utf-8")
        except OSError:
            raise UsageError("Claude login not found; run claude once to log in")
    try:
        oauth = json.loads(blob).get("claudeAiOauth") or {}
    except ValueError:
        raise UsageError("Claude credentials are not valid JSON")
    token = oauth.get("accessToken")
    if not token:
        raise UsageError("Claude login not found; run claude once to log in")
    expires = oauth.get("expiresAt")
    if isinstance(expires, (int, float)) and expires / 1000 < now.timestamp():
        raise UsageError("Claude login expired; run claude once to refresh")
    return token


def fetch_url(url, headers, timeout=TIMEOUT):
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        raise UsageError(f"Claude usage request failed: {error.reason if hasattr(error, 'reason') else error}")


def read_claude(token, fetch=fetch_url):
    """Return {"limits": [...], "complete": bool} from the Claude usage endpoint."""
    status, body = fetch(CLAUDE_USAGE_URL, {"Authorization": f"Bearer {token}",
                                            "anthropic-beta": "oauth-2025-04-20"})
    if status == 401:
        raise UsageError("Claude login expired; run claude once to refresh")
    if status != 200:
        raise UsageError(f"Claude usage endpoint returned HTTP {status}")
    try:
        limits = json.loads(body).get("limits")
    except (ValueError, AttributeError):
        raise UsageError("Claude usage reply is not valid JSON")
    if not isinstance(limits, list):
        raise UsageError("Claude usage reply has no limits array")
    return {"limits": limits, "complete": any(not entry.get("scope") for entry in limits)}


def claude_windows(limits, reserve):
    """Map the limits array onto Opus and Fable window lists."""
    result = {model: [] for model in CLAUDE_MODELS}
    for entry in limits:
        scope = entry.get("scope") or {}
        display = ((scope.get("model") or {}).get("display_name") or "") if scope else ""
        if scope and not display:
            continue   # scoped to a surface or unnamed model: not a Fable/Opus window
        targets = CLAUDE_MODELS if not scope else tuple(
            m for m in CLAUDE_MODELS if m in display.lower())
        label = f"Claude {entry.get('kind', 'limit')}" + (f" ({display})" if display else "")
        resets = entry.get("resets_at")
        row = window(label, entry.get("percent"), reserve, from_iso(resets) if resets else None)
        for model in targets:
            result[model].append(row)
    return result


# --- Assembly --------------------------------------------------------------

def normalize(codex_result, claude_result, reserve, now=None, missing=None):
    """Build the usage.json document choose-builder.py consumes.

    A provider result of None omits its models (unknown usage). `missing` maps a
    provider name to the reason its CLI is absent; those models are written as
    available: false so the selector excludes them.
    """
    now = now or datetime.now(timezone.utc)
    observed = iso(now)
    document = {}
    for provider, models in (("codex", CODEX_MODELS), ("claude", CLAUDE_MODELS)):
        if provider in (missing or {}):
            for model in models:
                document[model] = {"available": False, "source": missing[provider]}
    if codex_result is not None:
        windows = codex_windows(codex_result["windows"], reserve)
        for model in CODEX_MODELS:
            document[model] = {"available": True,
                               "source": "codex app-server account/rateLimits/read",
                               "observed_at": observed, "complete": codex_result["complete"],
                               "windows": windows[model]}
    if claude_result is not None:
        windows = claude_windows(claude_result["limits"], reserve)
        for model in CLAUDE_MODELS:
            document[model] = {"available": True,
                               "source": "Claude Code oauth usage endpoint",
                               "observed_at": observed, "complete": claude_result["complete"],
                               "windows": windows[model]}
    return document


def load_selector():
    spec = importlib.util.spec_from_file_location(
        "choose_builder", Path(__file__).resolve().with_name("choose-builder.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None, codex_reader=read_codex, claude_reader=None, which=shutil.which):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reserve", type=float, default=10,
                        help="reserve_percent for every window (default 10)")
    parser.add_argument("--providers", default="codex,claude",
                        help="comma-separated subset of codex,claude")
    parser.add_argument("--out", help="write the usage JSON here instead of stdout")
    parser.add_argument("--choose", metavar="LEVEL",
                        help="run choose-builder.py on the result and print its JSON "
                             "(low, high, scientific, or planner for the high planner)")
    args = parser.parse_args(argv)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    if not providers or any(p not in ("codex", "claude") for p in providers):
        parser.error("--providers must name codex and/or claude")
    if args.choose and args.choose not in ("low", "high", "scientific", "planner"):
        parser.error("--choose must be low, high, scientific, or planner")
    if not 0 <= args.reserve <= 100:
        parser.error("--reserve must be between 0 and 100")

    # A CLI missing from PATH is known unavailability; a read failure is unknown usage.
    results, missing = {}, {}
    readers = {"codex": codex_reader,
               "claude": claude_reader or (lambda: read_claude(claude_token()))}
    for provider in providers:
        if which(provider) is None:
            missing[provider] = f"{provider} CLI not on PATH"
            print(f"{provider}: {missing[provider]}", file=sys.stderr)
            continue
        try:
            results[provider] = readers[provider]()
        except UsageError as error:
            print(f"{provider}: {error}", file=sys.stderr)
    document = normalize(results.get("codex"), results.get("claude"), args.reserve,
                         missing=missing)
    text = json.dumps(document, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    if args.choose:
        try:
            result = load_selector().choose(args.choose, document)
        except (ValueError, TypeError, KeyError) as error:
            print(f"selector rejected the usage document: {error}", file=sys.stderr)
            return 2
        print(json.dumps(result, indent=2))
        return 0 if result["selected_model"] else 1
    if not args.out:
        print(text)
    return 0 if document else 1


if __name__ == "__main__":
    raise SystemExit(main())
