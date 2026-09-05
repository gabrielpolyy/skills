---
name: opus-codex
description: Software-development-engineer pipeline without Fable — Opus does the thinking, codex (Astra) does the reviewing. Opus (the main loop) plans and writes a near-final spec, an Opus subagent implements it, the planner checks the builder's delta against the spec, the codex-review skill (pinned to Astra at medium reasoning effort) runs the pipeline's code review and its findings are triaged and fixed until clean, and if the change is user-facing and the project has an e2e harness (e.g. a browser-e2e skill) an Opus subagent verifies the changed flow in the running app. Use when the user types /opus-codex with a task ("do this /opus-codex", "/opus-codex add X"), or asks for the pipeline on Opus and codex only (no Fable).
user-invocable: true
---

# Skill: opus-codex (plan and build with Opus, review with codex)

The engineering loop on a fixed model budget: **Opus and codex's Astra model
only — Fable is never spawned.** ("Astra" is the reviewer the `codex-review`
skill pins, at medium reasoning effort; the exact model id lives only at the top
of that skill's `review.sh`.)

1. **Plan** — Opus (the main loop) reads the code and writes a near-final spec.
2. **Build** — an Opus subagent implements the spec and runs the tests.
3. **Review** — the planner checks the builder's delta against the spec, then
   the `codex-review` skill runs the pipeline's code review — not a second
   opinion, *the* review; the planner triages and drives fixes until codex is
   clean.
4. **E2E** — if the change is user-facing and the project has an e2e harness,
   an Opus subagent verifies the changed flow in the running app.

**This skill assumes the main loop is Opus.** If it isn't, stop and tell the
user to switch (`/model`) — or, if they're on Fable, that `/fable-codex`
is the pipeline for that model. Don't plan on a cheaper model, and don't spend
Fable on a pipeline built to avoid it.

**Requires:** the `codex-review` skill installed (same repo) and the `codex`
CLI on `PATH`. Codex is the only code reviewer here — if either is missing,
stop after step 3, tell the user the review gate could not run, and suggest
installing codex. Never present the result as "reviewed" without it.

## Workflow

### 1. Plan (main thread)

- The task is whatever the user typed around the command. If it's genuinely
  ambiguous, ask (`AskUserQuestion`) **before** planning — never punt open
  decisions to the builder.
- Read the relevant code yourself and resolve the real design decisions.
- Write a **near-final spec** to the scratchpad dir as `spec.md`, self-contained:
  - **Exact files** to touch (absolute paths) and, for each, exactly what changes.
  - **Near-final code** — signatures, actual logic/SQL, wiring. Give the builder
    the code, not a description of it. Exception: large mechanical changes (same
    pattern across many files, bulk renames), where writing near-final code costs
    as much as building — spec those at design level with one worked example.
  - **Tests** — the exact test command, the test file to extend, the
    highest-value regression assertions. For a bug fix, require red-green: the
    regression test must be shown failing before the production change.
  - **Guardrails** — match existing style; touch nothing outside the listed
    files; no drive-by refactors.
  - **Definition of done** — tests green, and the specific behaviors that must hold.
- Too small to spec (a one-liner, a rename)? Say so, do it inline, and jump to
  step 4.

### 2. Build (Opus subagent)

Snapshot the tree first — working trees often carry unrelated uncommitted work,
and every later step must be scoped to the builder's changes only:

```
git status --porcelain > <scratchpad>/baseline.txt
git rev-parse HEAD > <scratchpad>/head.txt
```

Then launch one subagent, synchronous, with the spec path:

```
Agent(subagent_type: "general-purpose", model: "opus", run_in_background: false,
      description: "Implement <thing> per spec",
      prompt: "Implement exactly the spec at <abs path>/spec.md. Work only in
               <repo>. Touch only the files it lists; make no other changes.
               Do NOT commit, stash, or otherwise change git state — leave
               every change uncommitted in the working tree; the uncommitted
               diff is what gets reviewed next.
               If the spec marks the task as a bug fix, write the regression
               test first, run it, and capture its FAILING output before
               applying the production change. When done, run <test command>
               and report: the exact files you created and the exact files you
               modified (two lists), the failing-then-passing output for a bug
               fix, the test output, and any deviation from the spec and why.")
```

The builder is a separate subagent even though the main loop is already Opus —
a separate builder context keeps the planner's context clean for review.

### 3. Spec check (main thread)

Look at the work before handing it to codex:

- **Scope to the builder's delta — never bare `git diff`** (it mixes in
  pre-existing uncommitted work and misses files the builder *created*). Read
  `git diff -- <modified files>` plus every created file in full. Cross-check
  the builder's lists against `git status --porcelain` vs `baseline.txt` — any
  unlisted change is a stray edit to chase down.
- Confirm `git rev-parse HEAD` still matches `head.txt`. A builder that
  committed has hidden its delta from the review: `git reset --soft <that
  hash>` to undo, then continue as uncommitted work.
- Check the delta matches the spec's design. For a bug fix, confirm the test
  went red before the fix. Re-run the test command yourself.
- Misses go back to the **same** builder via `SendMessage` (its context is
  intact); repeat until clean. If the builder had to guess, tighten the spec.
- Keep the list of files the builder touched (created + modified, from the
  baseline diff) — step 4 hands it to the reviewer.

### 4. Code review (codex-review skill — the pipeline's reviewer)

Invoke the `codex-review` skill via the Skill tool and follow **its** loop:
pass `--paths` with the builder's file list from step 3 (so codex diffs only
the delta, not whatever else is uncommitted) plus a session-scope summary
built from the spec, read the findings, triage them yourself, fix the valid
ones, re-review — carrying the dismissed findings forward in the scope text as
that skill describes — until codex is clean or nothing new and valid remains.
This command is the user's explicit request for that review — don't ask again.

This is the pipeline's only code review, so don't soft-pedal the loop: run it
to a genuine stop condition (clean, no new valid findings, or the skill's
round backstop), never "one round was probably enough".

### 5. E2E verification (Opus subagent, when possible and needed)

Run only when **both** hold:

- **Needed** — the change affects behavior a user actually reaches (UI, routes,
  flows). Skip for refactors, test-only, doc, or internal tooling changes.
- **Possible** — the project has a real way to drive the running app (an e2e
  skill like `browser-e2e`, a `run`-style skill, or a documented dev-server +
  browser path). Don't build a harness from scratch for this.

Delegate the drive to a synchronous Opus subagent that invokes the project's
e2e skill and walks the **changed flow specifically**, reporting pass/fail per
step and screenshot paths. Read the verdict and key screenshot yourself.
Breakage loops back to the same builder, then re-verify. If e2e fixes changed
code after codex's last clean verdict, run one more codex round on that delta.

If either condition fails, skip — but say so in the report (one line: why).

### 6. Report

Verify scope one last time: `git status --porcelain` vs `baseline.txt` must
show exactly the spec's files plus approved fix-loop additions.

Then summarize: what shipped (files + behavior), test status, what codex
flagged and what you fixed vs. skipped (one-line reasons), the e2e outcome (or
why skipped), and any spec deviation you accepted.

### 7. Notify (Telegram)

After the report, tell the user's Telegram the run is over — also when the
pipeline stopped early (say why in the message). Source
`~/.config/telegram-notify/env` (it defines `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`) and send a one-line summary:

```bash
if [ -f ~/.config/telegram-notify/env ]; then
  . ~/.config/telegram-notify/env
  msg='✅ /opus-codex done in <repo>: <task> — tests <status>, review <status>'
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

- **No Fable.** This pipeline never spawns a subagent above Opus; the
  independent quality gate is codex. If the user wants Fable gates, that's
  `/fable-codex`.
- **The planner owns correctness.** Codex reviews the code, but the spec check
  in step 3 always happens — an unread diff never ships.
- **Fixes bypass earlier verdicts.** Code changed after codex's last clean
  verdict gets one more codex round (step 5).
- **Stop conditions.** Build loop: delta matches spec, tests green. Codex loop:
  per the codex-review skill. E2E: changed flow works, or skipped with a
  stated reason.
