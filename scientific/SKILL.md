---
name: scientific
description: Investigate, implement, and independently validate uncertain algorithms or scientific methods with Astra and Fable, choosing implementation by remaining quota. Use only for /scientific or an explicit request for the scientific workflow by name.
---

# Scientific

Use this profile with the required [shared workflow](../shared/workflow.md),
which covers invocation, repository location, dispatch, and usage.

| Stage | Models and effort |
|---|---|
| Coordinate | REQUIRED Fable high or Astra medium; the coordinator reconciles the planners and judges the reproduction |
| Plan | Astra high + Fable xhigh |
| Implement | Astra medium OR Fable high, selected by remaining quota |
| Review | The other model: Astra medium OR Fable high, in a fresh context |

The orchestrating session itself must run Fable (high) or Astra (medium).
If it runs any other model, stop before dispatching any role and ask the user
to switch the session model or restart from a Fable or Astra session; do not
coordinate scientific work from Sol, Opus, or a smaller model.

Have Astra and Fable independently examine the problem and raw evidence
before reading each other's proposal. Independent planning may run in
parallel. Reconcile their approaches and record unresolved uncertainty.

The agreed brief must include assumptions, hypotheses, a baseline, data and
provenance, metrics, acceptance criteria, and a reproducible experiment plan.
Specify seeds and data splits when applicable. Define numerical tolerances,
boundary cases, and how to detect regressions. Distinguish measured results
from claims that still need evidence; agreement between models is not proof.

Recheck usage AFTER both planning contributions. Choose the eligible builder
with the most usable quota, while reserving capacity on the OTHER model for
review. Planning runs at Astra high and Fable xhigh because that is where the
method is decided and it is cheap; implementation and reproduction are long
and would exhaust the pool at xhigh, so they run at Astra medium and Fable
high. A user can request a higher effort explicitly.

## Results record

The brief names a results record path (default `experiments/<task-slug>/RESULTS.md`
unless the project has a convention) and the builder must leave it there
with: the exact command(s), seed(s), data split or input provenance, metrics
against the predeclared acceptance criteria, environment (interpreter and key
package versions), and wall time.

## Validation run and review

Before the read-only review, the coordinator dispatches a separate validation
run by the REVIEWING model in a scratch worktree, with write access limited to
that tree:

```bash
scratch="$(mktemp -d)/repro"
git -C "$target_repo" worktree add --detach "$scratch" HEAD
git -C "$target_repo" diff HEAD | git -C "$scratch" apply   # then copy untracked task files
codex exec --sandbox workspace-write -C "$scratch" -m gpt-6-astra \
  -c model_reasoning_effort=medium -o "$repro_output" - < "$repro_brief"
# Fable: run inside "$scratch": claude -p --model fable --effort high \
#   --permission-mode acceptEdits --no-session-persistence < "$repro_brief"
git -C "$target_repo" worktree remove --force "$scratch"
```

The brief asks it to reproduce the critical experiment from the results
record and write its own record beside it. Then the same model reviews the
method, code, and experimental evidence read-only through the shared review
helper; its verdict must cite the reproduction output or state that
reproduction did not occur. It should challenge assumptions and independently
check decisive calculations. Inspect results against the predeclared
criteria, including failures and limitations. Do not tune the evaluation
merely to get a passing result.

Cross-model review is required at this level. If the other model is exhausted
or unavailable, preserve the completed work and report pending review. Do not
substitute a same-model review or declare the scientific result verified.
