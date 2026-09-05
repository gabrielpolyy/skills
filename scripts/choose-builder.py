#!/usr/bin/env python3
"""Choose from the profile's builder pool using observed quota, never credentials."""

import argparse
from datetime import datetime, timezone
import json
import math


POOLS = {"low": ("sol", "opus"), "high": ("sol", "opus"),
         "scientific": ("astra", "fable")}
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


def observation(row, now):
    if row is None:
        return None, "usage unknown"
    if not isinstance(row, dict):
        raise ValueError("model observation must be an object")
    available = row.get("available", True)
    if not isinstance(available, bool):
        raise ValueError("available must be a boolean")
    if not available:
        return -1, "unavailable"
    if not row.get("observed_at") or not row.get("source"):
        return None, "usage unknown: missing timestamp/source"
    age = (now - timestamp(row["observed_at"])).total_seconds()
    if age < 0 or age > 300:
        return None, "usage unknown: stale or future observation"
    windows = row.get("windows")
    if not windows or row.get("complete") is not True:
        return None, "usage unknown: incomplete limits"
    if not isinstance(windows, list):
        raise ValueError("windows must be a list")
    scores = []
    for window in windows:
        if not isinstance(window, dict) or not window.get("name"):
            raise ValueError("each window needs a name")
        if window.get("resets_at") and timestamp(window["resets_at"]) <= now:
            return None, "usage unknown: window reset; refresh observation"
        # Reserve is explicit; zero is valid when this pool needs no reserve.
        scores.append(percent(window["remaining_percent"]) -
                      percent(window["reserve_percent"]))
    return min(scores), "measured usable headroom"


def choose(level, data, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(data, dict):
        raise ValueError("usage input must be an object keyed by model")
    pool = POOLS[level]
    states = {model: observation(data.get(model), now) for model in pool}
    viable = [model for model in pool
              if states[model][0] is None or states[model][0] > 0]
    if level == "scientific":
        def can_review(model):
            score = states[model][0]
            return score is None or (score >= 0 and all(
                window["remaining_percent"] > 0
                for window in data[model]["windows"]))
        viable = [model for model in viable
                  if can_review(pool[1] if model == pool[0] else pool[0])]
    complete = all(score is not None for score, _ in states.values())
    measured = [model for model in viable if states[model][0] is not None]
    selected = max(measured, key=lambda model: states[model][0]) if measured else (
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
            "observations": {m: {"usable_remaining_percent": s, "status": r}
                             for m, (s, r) in states.items()}}


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
