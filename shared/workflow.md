# Shared engineering workflow

Read this together with the selected low, high, or scientific profile. The
profile controls model eligibility and effort; this file controls execution.
The three skill folders and their sibling `shared/` and `scripts/` directories
must stay together in the repository. Install by linking the skill folders,
not by copying an individual folder away from its supporting files.

## Invocation and location

A workflow runs only when the user types its slash command or asks for it by
name. Description matching alone grants nothing. That explicit invocation, and
only it, authorizes the workflow's planning, builder, review, and verification
agents within the user's task scope; a reviewer is never dispatched unless the
user asked for the workflow or for a review. Delegate these roles explicitly;
the main session can coordinate regardless of its model, except that
scientific requires a Fable or Astra orchestrator. Each profile names a
coordinator model, because reconciling plans, writing the brief,
triaging findings, and stopping the fix loop is judgment work; coordination
spends the coordinating CLI's quota, which the fetcher measures live. The
coordinator never performs a role itself, even when its model matches the
role's model, because every role needs a fresh context.

When a skill is installed through a symlink or Windows junction, relative
links resolve against the physical repository. With `$skill_dir` set to the
skill's base directory, locate the repository before following them:

```bash
skills_repo="$(python3 -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$skill_dir")"
```

## Model dispatch

Use explicit model AND effort on every delegated call. The coordinator does
not have to be the planner's model. Do not ask the user to switch their main
session when a CLI can dispatch the required model, except that scientific
requires a Fable or Astra orchestrator. Check actual runtime
capabilities; never pretend a different model performed a role.

| Role model | Codex model ID / Claude alias | Effort |
|---|---|---|
| Sol | `gpt-5.6-sol` | xhigh for every role |
| Opus | `opus` | xhigh for every role |
| Astra | `gpt-6-astra` | high ONLY for scientific planning; medium otherwise |
| Fable | `fable` | xhigh for scientific planning; high otherwise |

`opus` and `fable` are family aliases; the coordinator reports the resolved
model the CLI prints. Do not rely on inherited effort, the app model picker,
or automatic fallback models. Check CLI help if the installed version rejects
a flag. Report unavailable required capabilities without substituting a
cheaper pool or claiming a completed stage.

The `codex` CLI is the Codex route and `claude -p` is the Claude route. Native
Claude agents cannot pin reasoning effort (the Agent tool takes a model only),
so they are not used for these roles. Implementation and review go through
the shared helpers, which take a backend, model, and effort; the prompt rules,
baseline snapshot, post-run checks, and output contract are the same for both
CLIs. Set `skills_repo` as above, `target_repo` to the project root, and
`spec_file` to a written brief. These variables are local to the task:

```bash
# Sol builder (low/high). For Opus: IMPLEMENT_BACKEND=claude IMPLEMENT_MODEL=opus.
IMPLEMENT_BACKEND=codex IMPLEMENT_MODEL=gpt-5.6-sol IMPLEMENT_EFFORT=xhigh \
  bash "$skills_repo/scripts/implement.sh" "$spec_file" "$target_repo"
# Its first output line is `SNAPSHOT: <file>`; keep that path for the review.

# Fable reviewer (high/scientific). For Astra: REVIEW_BACKEND=codex
# REVIEW_MODEL=gpt-6-astra REVIEW_EFFORT=medium; low uses Sol or Opus at xhigh.
REVIEW_BACKEND=claude REVIEW_MODEL=fable REVIEW_EFFORT=high \
  bash "$skills_repo/scripts/review.sh" --baseline "$snapshot" --paths "$changed_paths" "$scope" "$target_repo"
```

Builders run under `codex exec --sandbox workspace-write` or `claude -p
--permission-mode acceptEdits`: both allow file edits inside the project and
nothing more, and the workflow invocation authorizes them. Never use
`bypassPermissions`. Reviewers and planners get `--sandbox read-only` on Codex
and `--tools Read,Glob,Grep --strict-mcp-config` on Claude. The helpers run
for many minutes: run each helper or role CLI as one background command and
wait for the harness's completion notification; do not start separate polling
loops. If a liveness check is unavoidable, test the recorded pid with
`kill -0`, or use a bracketed pattern such as `pgrep -f '[c]odex exec'` that
cannot match its own shell, and give the loop a deadline. Before reporting
completion, list the session's background tasks and stop only the ones this
workflow started. A `KILLED:` line or exit 143 is an incomplete stage, as are
`NO_CHANGES`, `ERROR:`, empty output, and `WARNING:` lines.

`--baseline` takes the snapshot implement.sh printed, so the review judges the
task delta against the pre-task state rather than HEAD. `--range
<base>..<head>` reviews committed work and prints the resolved object IDs.
`--paths` is whitespace-separated and cannot represent filenames containing
whitespace; for those, omit it and give the exact path list in the scope. For
multiple repos, pass each repo after the scope; use separate scoped calls if
their path lists differ. Do not commit before review unless you review with
`--range`.

For planning, pipe a self-contained brief to a fresh read-only call run from
the target project:

```bash
codex exec --sandbox read-only -m gpt-6-astra -c model_reasoning_effort=medium \
  -o "$plan_output" - < "$planning_brief"
claude -p --model fable --effort high --tools Read,Glob,Grep --strict-mcp-config \
  --no-session-persistence < "$planning_brief" > "$plan_output"
```

High plans with one of these, selected by quota with `--choose planner`;
scientific plans with both at Astra high and Fable xhigh; low plans with Sol
or Opus xhigh. Claude planners and reviewers have no shell: put the actual diff and
test evidence in the brief (review.sh embeds the delta for the claude
backend). Read-only planners can inspect local evidence; have the coordinator
obtain authorized external research needed for scientific work and supply
it. If tests cannot execute in a role's sandbox, the coordinator runs the
authorized test commands and supplies results. These CLI calls are separate
sessions: write the necessary context into their briefs, using stdin rather
than interpolating task prose into shell code. Do not launch nested workflow
skills from a role agent. Return each role's result to the coordinator.

## Usage-based assignment

Immediately before implementation, and again before any handoff, run the
usage fetcher with the selector for the profile:

```bash
python3 "$skills_repo/scripts/fetch-usage.py" --reserve 10 --choose low
```

It reads each CLI's own usage endpoint (`codex app-server` and the endpoint
behind Claude's `/usage`) and prints the selection. A user-pasted fresh
snapshot in [usage-format.md](usage-format.md) is an acceptable alternative.
A CLI missing from PATH is recorded as `available: false` for its models and
excludes them; a provider whose quota could not be read is omitted as unknown.
If the fetcher reads neither provider, use the disclosed fallback without
asking the user. The fetcher reads the CLI's stored login only to call the
provider's own usage endpoint and never prints it; no other credential access
is allowed. Do not equate session token totals or dollars with remaining
subscription quota. CLI availability alone is not evidence of quota.

For each eligible builder, consider every applicable limit: short window,
weekly/provider shared pool, and model-specific caps. Use the smallest
remaining percentage after a task-appropriate reserve for required review
and fixes. Reset times invalidate expired observations; refresh observations
older than five minutes. Missing limits or missing usage make that
candidate's usage unknown, not zero used or unlimited. Distinguish a reported
absence of a cap from a cap you failed to read.

Choose the model with the largest usable remaining percentage. If either
candidate's quota is unknown, an optimal comparison is impossible: state the
unknown explicitly and use a known viable candidate; if both are unknown,
default to Sol for low/high and Astra for scientific and the high planner
among available models.
Never describe a fallback as a measured lowest-usage choice. An explicit user
model preference takes precedence. Equal known headroom uses the same stable
tie-break order. Do not silently buy API credits to bypass a subscription cap.

Use the selector's `comparison_complete` and `reason` fields in the routing
report. An unavailable/zero-headroom result is not permission to expand the
model pool. Scientific also requires review capacity on the other model; the
selector excludes a known-unavailable or exhausted opposite reviewer and lets
review spend the reserve. Unknown review capacity must be disclosed. For high,
rank the Astra/Fable pool with `--choose planner` before planning, and
separately check and reserve Astra/Fable review capacity because its reviewer
pool differs from the builder pool; the review prefers the model not used for
planning.

Keep the selected builder through implementation and fixes. Reassign only
after an actual limit, unavailability, or inability to finish, stopping the
old writer before starting the next. Supply the current diff, test results,
remaining work, and reason for handoff. No concurrent writers on the same
task. A builder change in scientific also changes who must perform the final
cross-model review; report any mixed authorship to that reviewer.

## Delivery and mandatory review

1. Read project instructions and inspect relevant code. Before any writes,
   record HEAD, status, staged/unstaged patches, and contents of pre-existing
   untracked files; implement.sh writes exactly this snapshot and prints its
   path. A status-only snapshot cannot identify new edits to already-dirty
   files. Preserve the user's work; prefer an isolated checkout when
   overlapping edits cannot be distinguished safely. Never reset/stash the
   user's changes automatically.
2. Run the profile's planning roles. Produce one self-contained brief with
   behavioral requirements, files, contracts, resolved design decisions,
   meaningful verification commands, and acceptance criteria. Include the
   project rules and execution constraints each delegated agent needs.
3. Select implementation by usage and dispatch one builder. Inspect its real
   delta against the captured baseline and brief, including new files. A
   builder's summary is not evidence that the spec was met. Run appropriate
   checks and required regression tests; avoid broad repeat runs without a
   concrete reason. Do not inline a tiny change to bypass the assigned roles.
4. Always run the profile's independent review in a fresh context with the
   review helper and `--baseline`. Supply the brief, exact task delta, test
   results, and scope exclusions in the scope. The reviewer reads code and
   reports concrete correctness/contract findings, ordered P0–P3 with file
   and line references in ordinary Markdown. A clean review says
   `NO_FINDINGS`. Reviewers do not implement fixes. If the entire task is
   already satisfied without a diff, independently verify that behavior and
   report the no-op explicitly.
5. Triage findings against evidence. Have the assigned builder fix valid ones,
   run affected checks, then re-review the changed delta. Carry dismissed
   findings and reasons forward; ignore stylistic preferences and repeated
   unsupported claims. After three unsuccessful fix/review rounds, stop the
   loop and report the remaining concrete blocker rather than claiming clean
   review or consuming quota indefinitely.
6. E2E verification is conditional. Run it only when the project has an
   existing E2E harness or documented browser path AND either the user asked
   for E2E or the change is user-facing and the coordinator can run it with
   the session's own tools. Do not create a new harness for this workflow.
   Record pass/fail and evidence, or the specific reason it could not run.
   E2E-triggered fixes and re-reviews count toward the same three-round cap.
7. Report behavior changed, actual models/efforts, quota evidence or fallback,
   tests, review/fixes, E2E outcome, and remaining uncertainty. Review and
   required verification must finish before calling the task complete.

The workflow itself adds no permission to commit, push, deploy, delete data,
or notify other people. Honor existing user authorization for those actions;
do not add redundant approval steps. Do not send Telegram or other messages
merely because a previous version of these skills did so.
