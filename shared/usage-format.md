# Normalizing quota observations

`python3 scripts/fetch-usage.py` is the normal source of observations. It
reads `codex app-server` and the Claude usage endpoint, writes this format,
and with `--choose LEVEL` runs the selector on the result. Hand-written JSON
in this format is the fallback when the fetcher cannot read a provider or the
user pastes a fresh snapshot; run `python3 scripts/choose-builder.py low
/path/to/usage.json` on such a file (relative to this repository, or by
absolute path). Python 3 is required. The selector performs no network calls
and never reads authentication files.

The top-level JSON keys are `sol`, `opus`, `astra`, and `fable`; include the
two builder candidates for the chosen level. Omitted models have unknown
usage: the fetcher omits a provider whose quota it could not read (no login,
timeout, HTTP error, bad reply) and prints the reason on stderr. A CLI that is
not on PATH is known unavailability instead: the fetcher writes its models as
`{"available": false, "source": "codex CLI not on PATH"}` (or `claude CLI not
on PATH`), and the selector excludes them. Each observed candidate has this
shape (replace all example values with fresh measurements; the timestamps
below are illustrative):

```json
{
  "sol": {
    "available": true,
    "source": "codex app-server account/rateLimits/read",
    "observed_at": "2026-09-05T10:00:00Z",
    "complete": true,
    "windows": [
      {"name": "shared short window", "remaining_percent": 70,
       "reserve_percent": 10, "resets_at": "2026-09-05T12:00:00Z"},
      {"name": "shared weekly", "remaining_percent": 40,
       "reserve_percent": 5}
    ]
  },
  "opus": {"available": false}
}
```

Include every applicable provider/shared/model-specific window and explicitly
mark `complete: true` only when all limits are accounted for. If a shared pool
applies to two models, use the same observation for that pool on both; include
any extra model cap separately. Convert a reported used percentage with
`100 - used_percent`. Do not infer a quota percentage from token consumption.

`reserve_percent` is a percentage-point estimate of capacity to retain for
required review/fixes and other already-committed work in that window. Choose
it for the actual task; there is no universal reserve that guarantees a run
will fit. The smallest `remaining_percent - reserve_percent` is the candidate's
usable headroom. Resets invalidate an observation rather than granting assumed
fresh quota. Observations older than five minutes become unknown.

Missing/incomplete/stale data produces an explicitly labeled fallback.
Unavailable models and models with zero/negative usable headroom are excluded.
A window at zero remaining excludes the model as exhausted even when the rest
of the observation is incomplete or stale: known exhaustion beats unknown
completeness. Scientific excludes an allocation if the other model is known
unavailable or exhausted, since it must review; the reserve is not subtracted
for that check, because it is held for this task's review and fixes and review
may spend it. For high, the `high` level ranks Sol/Opus builders only; the
`planner` level ranks Astra/Fable for its single planner, defaulting to Astra
when both are unknown. Check Astra/Fable review capacity separately. Recheck
quota at handoff if other sessions may have consumed a shared pool.

Exit 0 means a builder or disclosed fallback was selected. Exit 1 means no
allocation is viable; retain work and report the capacity issue. Exit 2 means
invalid input; correct it rather than treating it as unknown usage.
