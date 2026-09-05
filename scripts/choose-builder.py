#!/usr/bin/env python3
"""Choose from the profile's builder pool using observed quota, never credentials.

Levels low/high/scientific rank that profile's builders. Level planner ranks
Astra/Fable for the high profile's single planner; pool order defaults to Astra.
"""

import argparse
from datetime import datetime, timezone
import json
import math


POOLS = {"low": ("sol", "opus"), "high": ("sol", "opus"),
         "scientific": ("astra", "fable"), "planner": ("astra", "fable")}
EFFORT = {"sol": "xhigh", "opus": "xhigh", "astra": "medium", "fable": "high"}


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("percentages must be numbers")
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("percentages must be finite and between 0 and 100")
    return value


# Observation status: the score is a number ONLY for MEASURED; every other
# status carries no score, so a negative measured score is never mistaken for
# "unavailable" or "exhausted".
UNAVAILABLE, EXHAUSTED, UNKNOWN, MEASURED = "unavailable", "exhausted", "unknown", "measured"


def observation(row, now):
    """Return (status, usable_score_or_None, reason) for one model's row."""
    if row is None:
        return UNKNOWN, None, "usage unknown"
    if not isinstance(row, dict):
        raise ValueError("model observation must be an object")
    available = row.get("available", True)
    if not isinstance(available, bool):
        raise ValueError("available must be a boolean")
    if not available:
        return UNAVAILABLE, None, row.get("source") or "unavailable"
    windows = row.get("windows")
    if windows is not None and not isinstance(windows, list):
        raise ValueError("windows must be a list")
    # Known exhaustion beats unknown completeness: any unreset window at zero
    # excludes the model even when the rest of the observation is unusable.
    for window in windows or []:
        if not isinstance(window, dict) or not window.get("name"):
            raise ValueError("each window needs a name")
        if window.get("resets_at") and timestamp(window["resets_at"]) <= now:
            continue
        if percent(window["remaining_percent"]) <= 0:
            return EXHAUSTED, None, "exhausted"
    if not row.get("observed_at") or not row.get("source"):
        return UNKNOWN, None, "usage unknown: missing timestamp/source"
    age = (now - timestamp(row["observed_at"])).total_seconds()
    if age < 0 or age > 300:
        return UNKNOWN, None, "usage unknown: stale or future observation"
    if not windows or row.get("complete") is not True:
        return UNKNOWN, None, "usage unknown: incomplete limits"
    scores = []
    for window in windows:
        if window.get("resets_at") and timestamp(window["resets_at"]) <= now:
            return UNKNOWN, None, "usage unknown: window reset; refresh observation"
        # Reserve is explicit; zero is valid when this pool needs no reserve.
        scores.append(percent(window["remaining_percent"]) -
                      percent(window["reserve_percent"]))
    return MEASURED, min(scores), "measured usable headroom"


def choose(level, data, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(data, dict):
        raise ValueError("usage input must be an object keyed by model")
    pool = POOLS[level]
    states = {model: observation(data.get(model), now) for model in pool}
    status = {model: states[model][0] for model in pool}
    score = {model: states[model][1] for model in pool}
    viable = [model for model in pool
              if status[model] == UNKNOWN or (status[model] == MEASURED and score[model] > 0)]
    if level == "scientific":
        # The other model must review: it is viable unless known unavailable or
        # exhausted. Reserve is not subtracted; review may spend it, so a
        # measured score at or below zero still counts as a viable reviewer.
        viable = [model for model in viable
                  if status[pool[1] if model == pool[0] else pool[0]] not in (UNAVAILABLE, EXHAUSTED)]
    complete = all(value == MEASURED for value in status.values())
    measured = [model for model in viable if status[model] == MEASURED]
    selected = max(measured, key=lambda model: score[model]) if measured else (
        viable[0] if viable else None)
    if not selected:
        reason = "No viable builder/reviewer allocation within the profile."
    elif complete:
        reason = "Largest usable remaining percentage; pool order breaks ties."
    else:
        reason = "Usage comparison incomplete; known viable candidate or pool-order fallback."
    return {"level": level, "selected_model": selected,
            "effort": EFFORT.get(selected), "comparison_complete": complete,
            "reason": reason,
            "observations": {m: {"usable_remaining_percent": s, "status": st, "reason": r}
                             for m, (st, s, r) in states.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", choices=POOLS)
    parser.add_argument("usage_file")
    args = parser.parse_args()
    try:
        with open(args.usage_file, encoding="utf-8") as stream:
            result = choose(args.level, json.load(stream))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0 if result["selected_model"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
