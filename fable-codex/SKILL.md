---
name: fable-codex
description: Software-development-engineer pipeline with Fable designing and codex building — Fable (the main loop) plans and writes a near-final spec, the codex-implement skill (codex exec, workspace-write sandbox) implements it, Fable reviews the builder's delta against the spec (the pipeline's cross-model review), the codex-review skill (Sol) runs the external review pass and its findings are triaged and fixed until clean, and if the change is user-facing and the project has an e2e harness (e.g. a browser-e2e skill) an Opus subagent verifies the changed flow in the running app. Use when the user types /fable-codex with a task ("do this /fable-codex", "/fable-codex add X"), or asks for the Fable-designs, codex-implements pipeline in one shot.
user-invocable: true
---

# Skill: fable-codex (Fable designs, codex implements)

One command, a fixed division of labor:

1. **Plan** — Fable (the main loop) reads the code and writes a near-final spec.
2. **Build** — the `codex-implement` skill has codex implement the spec in a
   workspace-write sandbox and run the tests.
3. **Review** — Fable reads the builder's delta against the spec; with codex as
   the builder AND the external reviewer, this is the pipeline's only
   cross-model review — a real review, not a glance. Then the `codex-review`
   skill runs the external pass; Fable triages and drives fixes until clean.
4. **E2E** — if the change is user-facing and the project has an e2e harness,
   an Opus subagent verifies the changed flow in the running app.

**This skill assumes the main loop is Fable.** If it isn't, stop and tell the
user to switch (`/model`) — Fable's design and its read of codex's work are the
whole point; don't emulate the pipeline on a cheaper model.

**Requires:** the `codex-implement` and `codex-review` skills (same repo) and
the `codex` CLI on `PATH`. Codex is the builder here — if the CLI is missing
there is no pipeline; stop and tell the user to install it.

## Workflow

### 1. Plan (main thread)

- The task is whatever the user typed around the command. If it's genuinely
  ambiguous, ask (`AskUserQuestion`) **before** planning — never punt open
  decisions to the builder.
- Read the relevant code yourself and resolve the real design decisions.
- Write a **near-final spec** to the scratchpad dir as `spec.md`, self-contained:
  - **Exact files** to touch (repo-relative paths) and, for each, exactly what changes.
  - **Near-final code** — signatures, actual logic/SQL, wiring. Give the builder
    the code, not a description of it. Exception: large mechanical changes (same
    pattern across many files, bulk renames), where writing near-final code costs
    as much as building — spec those at design level with one worked example.
  - **Tests** — the exact test command, the test file to extend, the
    highest-value regression assertions. For a bug fix, say so explicitly and
    require red-green: the regression test must be shown failing before the
    production change.
  - **Guardrails** — match existing style; touch nothing outside the listed
    files; no drive-by refactors.
  - **Definition of done** — tests green, and the specific behaviors that must hold.
- The builder is a **one-shot external process**: it cannot ask questions,
  cannot be messaged mid-run, and starts with zero context. The spec must stand
  entirely alone — and must not require anything the sandbox blocks (no
  network, so no package installs or fetches).
- Too small to spec (a one-liner, a rename)? Say so, do it inline, and jump to
  step 4.

### 2. Build (codex-implement skill)

Snapshot the tree first — working trees often carry unrelated uncommitted work,
and every later step must be scoped to the builder's changes only:

```
git status --porcelain > <scratchpad>/baseline.txt
```

Then invoke the `codex-implement` skill via the Skill tool with the spec path
and follow **its** steps — it runs `implement.sh` (pinned to Sol at high
reasoning effort), which embeds the spec into the prompt, confines writes to
the repo, and warns when codex committed or the run changed nothing. Use a
generous Bash timeout (600000 ms). This command is the user's explicit request
to delegate the build — don't ask again.

### 3. Spec review (main thread)

The builder and the external reviewer are both codex — this read is the only
cross-model eyes on the diff, so treat it as the pipeline's real review:

- Do the `codex-implement` skill's **Verify** and **Fix loop** steps in full
  (delta scoped via `baseline.txt`, never bare `git diff`; every created file
  read whole; report lists cross-checked; tests re-run; red-green confirmed
  for a bug fix; misses fixed inline or via a new self-contained brief, with
  its 3-round backstop). That skill is the single description of those steps —
  don't improvise a lighter version here.
- On top of that, check every hunk against the **spec's design**, not just
  against the builder's report: the spec is yours, and this is where a builder
  that quietly redesigned something gets caught.
- Keep the list of files the builder touched (created + modified, from the
  baseline diff) — step 4 hands it to the reviewer.

### 4. External review (codex-review skill)

Invoke the `codex-review` skill via the Skill tool and follow **its** loop:
pass `--paths` with the builder's file list from step 3 (so codex diffs only
the delta, not whatever else is uncommitted) plus a session-scope summary
built from the spec, read the findings, triage them yourself, fix the valid
ones, re-review — carrying the dismissed findings forward in the scope text as
that skill describes — until codex is clean or nothing new and valid remains.
This command is the user's explicit request for that review — don't ask again.

The reviewer shares the builder's model family, but a fresh context under a
review prompt still catches real bugs — it supplements your step-3 read, never
replaces it.

### 5. E2E verification (when possible and needed)

Run only when **both** hold:

- **Needed** — the change affects behavior a user actually reaches (UI, routes,
  flows). Skip for refactors, test-only, doc, or internal tooling changes.
- **Possible** — the project has a real way to drive the running app (an e2e
  skill like `browser-e2e`, a `run`-style skill, or a documented dev-server +
  browser path). Don't build a harness from scratch for this.

Delegate the drive to a synchronous Opus subagent that invokes the project's
e2e skill and walks the **changed flow specifically**, reporting pass/fail per
step and screenshot paths (codex can't drive the project's e2e skills — this
step stays on a Claude subagent). Read the verdict and key screenshot yourself.
Breakage goes back through step 3's fix loop (inline or a new codex brief),
then re-verify. If e2e fixes changed code after codex's last clean verdict,
run one more codex round on that delta.

If either condition fails, skip — but say so in the report (one line: why).

### 6. Report

Verify scope one last time: `git status --porcelain` vs `baseline.txt` must
show exactly the spec's files plus approved fix-loop additions.

Then summarize: what shipped (files + behavior), test status, any spec
deviation the builder flagged or you accepted, what codex-review flagged and
what you fixed vs. skipped (one-line reasons), and the e2e outcome (or why
skipped).

### 7. Notify (Telegram)

After the report, tell the user's Telegram the run is over — also when the
pipeline stopped early (say why in the message). Source
`~/.config/telegram-notify/env` (it defines `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`) and send a one-line summary:

```bash
if [ -f ~/.config/telegram-notify/env ]; then
  . ~/.config/telegram-notify/env
  msg='✅ /fable-codex done in <repo>: <task> — tests <status>, review <status>'
  printf '%s' "$msg" | curl -fsS "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" --data-urlencode text@- >/dev/null \
    && echo TELEGRAM_SENT || echo TELEGRAM_FAILED
fi
```

Keep the message in **single quotes** so a task containing `"`, `$` or
backticks can't break the command (if the task text itself has a single quote,
drop or replace it). The text goes through stdin (`text@-`), not an argument:
on Windows, Git Bash mangles non-ASCII argv when spawning native curl.exe
(Telegram rejects it with "strings must be encoded in UTF-8"), while a pipe
carries raw UTF-8 intact. `-f` turns an HTTP error into a non-zero exit, which
is what makes `TELEGRAM_FAILED` reliable — without it curl exits 0 on a 400.

If the config file is missing, skip silently. On `TELEGRAM_FAILED`, mention it
in the report — never let notification failure affect the pipeline's result.

## Guardrails

- **You own correctness.** Codex builds and codex reviews — your step-3 read is
  the independent gate; an unread hunk never ships.
- **Fixes bypass earlier verdicts.** Code changed after codex-review's last
  clean verdict gets one more review round (step 5).
- **Uncommitted work only.** The builder must leave the tree uncommitted;
  `implement.sh` warns if HEAD moved — undo the commit before reviewing.
- **Stop conditions.** Build loop: delta matches spec, tests green (3-round
  backstop, then finish inline). Review loop: per the codex-review skill. E2E:
  changed flow works, or skipped with a stated reason.
