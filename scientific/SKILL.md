---
name: scientific
description: Investigate, implement, and independently validate uncertain algorithms or scientific methods with Astra and Fable, choosing implementation by remaining quota. Use for /scientific, signal processing, scoring mathematics, statistical evaluation, and work requiring hypotheses and reproducible experiments.
---

# Scientific

Use this profile with the required [shared workflow](../shared/workflow.md).
Resolve this skill's real repository location before following relative links
when installed through a symlink or Windows junction.

| Stage | Models and effort |
|---|---|
| Plan | Astra high + Fable xhigh |
| Implement | Astra medium OR Fable high, selected by remaining quota |
| Review | The other model: Astra medium OR Fable high, in a fresh context |

Delegate these roles explicitly; the main session can coordinate regardless of
its model. Have Astra and Fable independently examine the problem and raw
evidence before reading each other's proposal. Independent planning may run
in parallel. Reconcile their approaches and record unresolved uncertainty.

The agreed brief must include assumptions, hypotheses, a baseline, data and
provenance, metrics, acceptance criteria, and a reproducible experiment plan.
Specify seeds and data splits when applicable. Define numerical tolerances,
boundary cases, and how to detect regressions. Distinguish measured results
from claims that still need evidence; agreement between models is not proof.

Recheck usage AFTER both planning contributions. Choose the eligible builder
with the most usable quota, while reserving capacity on the OTHER model for
review. Astra drops to medium for implementation and review; Fable drops to
high. No automatic xhigh/max escalation for either implementation or review.

The other model reviews the method, code, and experimental evidence. It should
challenge assumptions and independently check decisive calculations or
reproduce the critical experiment in an isolated scratch workspace. Keep
review read-only against the implementation tree. A separate validation run
may write scratch outputs; report whether reproduction actually occurred.
Inspect results against the predeclared criteria, including failures and
limitations. Do not tune the evaluation merely to get a passing result.

Cross-model review is required at this level. If the other model is exhausted
or unavailable, preserve the completed work and report pending review. Do not
substitute a same-model review or declare the scientific result verified.
