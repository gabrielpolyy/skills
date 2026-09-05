---
name: high
description: Plan substantial software changes with Astra or Fable selected by remaining quota, delegate implementation to Sol or Opus by remaining quota, and require review by the other of Astra or Fable; also runs review-only work on an existing PR, delta, or audit findings. Use only for /high or an explicit request for the high workflow or its review by name.
---

# High

Use this profile with the required [shared workflow](../shared/workflow.md),
which covers invocation, repository location, dispatch, and usage.

| Stage | Models and effort |
|---|---|
| Coordinate | Recommended Fable high or Astra medium; Opus or Sol acceptable |
| Plan | Astra medium OR Fable high, selected by remaining quota |
| Implement | Sol xhigh OR Opus xhigh, selected by remaining quota |
| Review | Prefer the model NOT used for planning: Astra medium OR Fable high, in a fresh context |

## Review-only requests

When the user explicitly requests review of an existing PR, delta, or audit
findings, run only the review stage. Do not plan an implementation, dispatch a
builder, apply fixes, or enter the shared fix loop. This exception overrides
the shared delivery sequence; normal implementation requests still use every
stage below. Review existing evidence rather than starting a new audit.

Select Astra medium or Fable high using fresh remaining-quota evidence,
accounting for applicable shared/model caps. Unknown quota is a disclosed
fallback: prefer a known viable candidate, otherwise an available Astra, then
Fable. Never use Sol/Opus for the high review itself. Use a fresh context and
report the actual reviewer and effort. An unavailable reviewer, missing
evidence, or failed invocation is incomplete review, not a clean result.

Provide the precise review scope, requirements, baseline, delta or audit
evidence, and existing verification results. For a PR/commit range, resolve
the requested base/head (the merge base for a PR) and run the shared review
helper with `--range <base>..<head>` and the chosen backend; it prints the
resolved object IDs and gives the reviewer that exact diff, read-only. For an
uncommitted delta use `--paths` and, when available, `--baseline`. For audit
findings without a diff, pipe the evidence to a fresh read-only call as the
shared workflow shows for planners. Avoid unrelated working-tree changes.

Return concrete findings with severity, location, impact, and evidence, or
explicitly report no actionable findings within scope. Apply any user-specified
severity threshold. The reviewer only reports; an already-authorized parent
automation may publish or vote under its own policy after checking the result.
Review alone adds no permission to publish, approve, deploy, or change files.

## Implementation requests

Select ONE planner, Astra medium or Fable high, by usable headroom within the
Astra/Fable pool using the fetcher with the selector's `planner` level:

```bash
python3 "$skills_repo/scripts/fetch-usage.py" --reserve 10 --choose planner
```

Unknown quota is a disclosed fallback that defaults to Astra among available
models. The planner alone produces the self-contained implementation brief,
checked against the actual code, contracts, failure cases, and validation
strategy. Report the actual planner and effort.

Recheck usage after planning before choosing Sol or Opus to implement. Resolve
difficult design decisions in the plan; if the builder finds a new design
question, route it back to the planner instead of accepting an improvised
architecture.

Review prefers the model NOT used for planning: Fable high after an Astra
plan, Astra medium after a Fable plan. If that opposite model is unavailable
or exhausted, use the planning model in a fresh context and report that
fallback explicitly. Planning does not substitute for review of the finished
delta.

Escalate a scientific subproblem separately when the underlying method needs
investigation; explain the scope and proposed level change. Never silently
downgrade planning or review to Sol/Opus to get around depleted quota.
