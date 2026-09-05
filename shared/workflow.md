# Shared engineering workflow

Read this together with the selected low, high, or scientific profile. The
profile controls model eligibility and effort; this file controls execution.
The three skill folders and their sibling `shared/` and `scripts/` directories
must stay together in the repository. Install by linking the skill folders,
not by copying an individual folder away from its supporting files.

## Model dispatch

Use explicit model AND effort on every delegated call. The coordinator does
not have to be the planner's model. Do not ask the user to switch their main
session when a supported agent tool or CLI can dispatch the required model.
Check actual runtime capabilities; never pretend a different model performed
a role. Invoking one of these workflows authorizes its planning, builder,
review, and applicable verification agents within the user's task scope.

| Role model | Codex model ID / Claude alias | Effort |
|---|---|---|
| Sol | `gpt-5.6-sol` | xhigh for every role |
| Opus | `opus` | xhigh for every role |
| Astra | `gpt-6-astra` | high ONLY for scientific planning; medium otherwise |
| Fable | `fable` | xhigh for scientific planning; high otherwise |

Prefer native agent tools when they can explicitly select both the required
model and effort. Otherwise use the installed CLI. Do not rely on inherited
effort, the app model picker, or automatic fallback models. Check CLI help if
the installed version rejects a flag. Report unavailable required capabilities
without substituting a cheaper pool or claiming a completed stage.

For Codex implementation and review, use the preserved helpers with explicit
environment overrides. Set `skills_repo` to the physical repository root,
`target_repo` to the project root, and `spec_file` to a written brief. These
variables are local to the task, not global configuration:

```bash
# Sol builder (low/high); scientific uses gpt-6-astra / medium instead.
CODEX_IMPLEMENT_MODEL=gpt-5.6-sol CODEX_IMPLEMENT_EFFORT=xhigh \
  bash "$skills_repo/scripts/implement.sh" "$spec_file" "$target_repo"

# Astra reviewer (high/scientific); low uses gpt-5.6-sol / xhigh instead.
CODEX_REVIEW_MODEL=gpt-6-astra CODEX_REVIEW_EFFORT=medium \
  bash "$skills_repo/scripts/review.sh" --paths "$changed_paths" "$scope" "$target_repo"
```

The review helper's `--paths` is whitespace-separated and cannot represent
filenames containing whitespace. For those, omit `--paths` and give the exact
path list plus the baseline/delta artifacts in the scope. For multiple repos,
pass each repo after the scope; use separate scoped calls if their path lists
differ. The helper reviews uncommitted work, so do not commit before review.

For Codex planning, run from the target project and pipe a self-contained
planning brief to a fresh read-only invocation:

```bash
codex exec --sandbox read-only -m gpt-6-astra \
  -c model_reasoning_effort=medium -o "$plan_output" - < "$planning_brief"
```

Use Astra high in that command for scientific planning, or Sol xhigh for low.
Read-only planners can inspect local evidence; have the coordinator obtain
authorized external research needed for scientific work and supply it.

For Claude, native Opus/Fable agents are preferred. A CLI fallback for a
planner/reviewer is `claude -p --model fable --effort high --tools 'Read,Glob,Grep'
--strict-mcp-config --no-session-persistence < brief.md`, run in the target
project. This limits built-in tools to reading; provide the actual diff and
test evidence in the brief because shell tools are unavailable. For an Opus
role use `--model opus --effort xhigh`; scientific Fable planning uses xhigh.
For implementation, use `claude -p --model opus --effort xhigh
--permission-mode acceptEdits --no-session-persistence < spec.md` or Fable/high.
Preserve the environment's permissions. If tests cannot execute, the
coordinator runs the authorized test commands and supplies results. Never add
permission-bypass flags to make a stage pass. These CLI calls are separate
sessions: write the necessary context into their briefs, using stdin rather
than interpolating task prose into shell code. Do not launch nested workflow
skills from a role agent. Return its role's result to the coordinator.

## Usage-based assignment

Immediately before implementation, obtain fresh quota information from actual
provider/runtime usage surfaces (for example Claude's interactive `/usage`,
Codex's interactive `/status`, or an available documented quota tool). These
are interactive commands, not invented shell subcommands. A user-provided
fresh snapshot is also usable. Never expose credentials or scrape token files
to obtain quota. Do not equate session token totals or dollars with remaining
subscription quota. CLI availability alone is not evidence of quota.

For each eligible builder, consider every applicable limit: short window,
weekly/provider shared pool, and model-specific caps. Use the smallest
remaining percentage after a task-appropriate reserve for required review
and fixes. Use reported reset times to exclude expired observations; refresh
observations older than five minutes. Missing limits or missing usage make
that candidate's usage unknown, not zero used or unlimited. Distinguish a
reported absence of a cap from a cap you failed to read.

Choose the model with the largest usable remaining percentage. If either
candidate's quota is unknown, an optimal comparison is impossible: state the
unknown explicitly and use a known viable candidate; if both are unknown,
default to Sol for low/high and Astra for scientific among available models.
Never describe a fallback as a measured lowest-usage choice. An explicit user
model preference takes precedence. Equal known headroom uses the same stable
tie-break order. Do not silently buy API credits to bypass a subscription cap.

`scripts/choose-builder.py LEVEL usage.json` applies this rule to normalized
observations; it does not fetch quota. Read [usage-format.md](usage-format.md)
when preparing its input. Use its `comparison_complete` and `reason` fields
in the routing report. An unavailable/zero-headroom result is not permission
to expand the model pool. Scientific also requires usable review capacity on
the other model; the selector prevents a known-unavailable/exhausted opposite
reviewer. Unknown review capacity must be disclosed and checked when possible.
For high, separately check and reserve Astra/Fable review capacity because
its reviewer pool differs from the builder pool.

Keep the selected builder through implementation and fixes. Reassign only
after an actual limit, unavailability, or inability to finish, stopping the
old writer before starting the next. Supply the current diff, test results,
remaining work, and reason for handoff. No concurrent writers on the same
task. A builder change in scientific also changes who must perform the final
cross-model review; report any mixed authorship to that reviewer.

## Delivery and mandatory review

1. Read project instructions and inspect relevant code. Record HEAD, status,
   staged/unstaged patches, and contents of pre-existing untracked files that
   overlap the scope in scratch storage before any writes. A status-only
   snapshot cannot identify new edits to already-dirty files. Preserve the
   user's work; prefer an isolated checkout when overlapping edits cannot be
   distinguished safely. Never reset/stash the user's changes automatically.
2. Run the profile's planning roles. Produce one self-contained brief with
   behavioral requirements, files, contracts, resolved design decisions,
   meaningful verification commands, and acceptance criteria. Include the
   project rules and execution constraints each delegated agent needs.
3. Select implementation by usage and dispatch one builder. Inspect its real
   delta against the captured baseline and brief, including new files. A
   builder's summary is not evidence that the spec was met. Run appropriate
   checks and required regression tests; avoid broad repeat runs without a
   concrete reason. Do not inline a tiny change to bypass the assigned roles.
4. Always run the profile's independent review in a fresh context. Supply the
   brief, baseline, exact task delta, test results, and scope exclusions. The
   reviewer reads code and reports concrete correctness/contract findings,
   ordered P0–P3 with file and line references in ordinary Markdown. A clean
   review says `NO_FINDINGS`. Reviewers do not implement fixes. The helpers'
   `NO_CHANGES`, errors, empty output, and warnings are not clean verdicts.
   If the entire task is already satisfied without a diff, independently
   verify that behavior and report the no-op explicitly.
5. Triage findings against evidence. Have the assigned builder fix valid ones,
   run affected checks, then re-review the changed delta. Carry dismissed
   findings and reasons forward; ignore stylistic preferences and repeated
   unsupported claims. After three unsuccessful fix/review rounds, stop the
   loop and report the remaining concrete blocker rather than claiming clean
   review or consuming quota indefinitely.
6. For changed user-facing flows, use an existing E2E harness or documented
   browser path when available. Sol/Opus verification runs at xhigh, chosen by
   capability and capacity; it supplements the profile's mandatory reviewer.
   Do not create a new E2E harness solely for this workflow. Record pass/fail
   and evidence, or a specific reason verification could not run. E2E fixes
   require affected tests and another review of the changed delta.
7. Report behavior changed, actual models/efforts, quota evidence or fallback,
   tests, review/fixes, E2E outcome, and remaining uncertainty. Review and
   required verification must finish before calling the task complete.

The workflow itself adds no permission to commit, push, deploy, delete data,
or notify other people. Honor existing user authorization for those actions;
do not add redundant approval steps. Do not send Telegram or other messages
merely because a previous version of these skills did so.
