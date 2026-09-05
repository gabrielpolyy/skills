---
name: high
description: Plan substantial software changes with Astra and Fable, delegate implementation to Sol or Opus by remaining quota, and require Astra or Fable review. Also supports explicitly requested review-only work on an existing PR, delta, or audit findings using the high review stage.
---

# High

Use this profile with the required [shared workflow](../shared/workflow.md).
Resolve this skill's real repository location before following relative links
when installed through a symlink or Windows junction.

| Stage | Models and effort |
|---|---|
| Plan | Astra medium + Fable high |
| Implement | Sol xhigh OR Opus xhigh, selected by remaining quota |
| Review | Astra medium OR Fable high, in a fresh context |

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
the requested base/head and merge base to object IDs, inspect that exact
diff, and read surrounding code at the reviewed head. Do not use the shared
uncommitted-diff helper for committed PRs. Dispatch a fresh read-only Codex
call with Astra/medium, or a Fable/high agent with read-only tools and the
actual diff/evidence supplied. Avoid unrelated working-tree changes.

Return concrete findings with severity, location, impact, and evidence, or
explicitly report no actionable findings within scope. Apply any user-specified
severity threshold. The reviewer only reports; an already-authorized parent
automation may publish or vote under its own policy after checking the result.
Review alone adds no permission to publish, approve, deploy, or change files.

## Implementation requests

Delegate these roles explicitly; the main session can coordinate regardless of
its model. Pick a planning lead by capacity. The lead proposes a concrete plan;
the other model challenges it against the actual code, contracts, failure
cases, and validation strategy. Reconcile material disagreements into one
self-contained implementation brief. Both models must contribute to planning.

Recheck usage after planning before choosing Sol or Opus to implement. Resolve
difficult design decisions in the plan; if the builder finds a new design
question, route it back to the planners instead of accepting an improvised
architecture. Select the reviewer by remaining capacity within Astra/Fable.
A planning contribution does not substitute for review of the finished delta.

Escalate a scientific subproblem separately when the underlying method needs
investigation; explain the scope and proposed level change. Never silently
downgrade planning or review to Sol/Opus to get around depleted quota.
