# Normalizing quota observations

Run `python3 scripts/choose-builder.py low /path/to/usage.json` from this
repository, or use the script's absolute path. Python 3 is required. The
selector performs no network calls and never reads authentication files.

The top-level JSON keys are `sol`, `opus`, `astra`, and `fable`; include the
two builder candidates for the chosen level. Omitted models have unknown
usage. Each observed candidate has this shape (replace all example values
with fresh measurements; the timestamps below are illustrative):

```json
{
  "sol": {
    "available": true,
    "source": "Codex /status, observed in this session",
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
Scientific excludes an allocation if the other model is known unavailable or
exhausted, since it must review. For high, check Astra/Fable review capacity
separately; this helper ranks Sol/Opus builders only. Recheck quota at handoff
if other sessions may have consumed a shared pool.

Exit 0 means a builder or disclosed fallback was selected. Exit 1 means no
allocation is viable; retain work and report the capacity issue. Exit 2 means
invalid input; correct it rather than treating it as unknown usage.
