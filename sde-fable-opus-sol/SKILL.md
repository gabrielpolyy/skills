---
name: sde-fable-opus-sol
description: Software-development-engineer pipeline with a fixed division of labor — Fable (the main loop) plans and writes a near-final spec, an Opus subagent implements it, Fable checks the builder's delta against the spec, the codex-review skill (Sol) runs the external code review and its findings are triaged and fixed until clean, and if the change is user-facing and the project has an e2e harness (e.g. a browser-e2e skill) an Opus subagent verifies the changed flow in the running app. Use when the user types /sde-fable-opus-sol with a task ("do this /sde-fable-opus-sol", "/sde-fable-opus-sol add X"), or asks for the Fable-plans, Opus-builds, codex-reviews pipeline in one shot.
user-invocable: true
---

# Skill: sde-fable-opus-sol (Fable plans, Opus builds, Sol reviews)

One command, four roles:

1. **Plan** — Fable (the main loop) reads the code and writes a near-final spec.
2. **Build** — an Opus subagent implements the spec and runs the tests.
3. **Review** — Fable checks the builder's delta against the spec, then the
   `codex-review` skill runs an independent external review; Fable triages and
   drives fixes until codex is clean.
4. **E2E** — if the change is user-facing and the project has an e2e harness,
   an Opus subagent verifies the changed flow in the running app.

**This skill assumes the main loop is Fable.** If it isn't, stop and tell the
user to switch (`/model`) or run `/sde-opus-sol` instead — don't emulate the
pipeline on a cheaper model.

**Requires:** the `codex-review` skill installed (same repo) and the `codex`
CLI on `PATH`. If either is missing, run the other steps and tell the user the
codex review was skipped and why.

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
```

Then launch one subagent, synchronous, with the spec path:

```
Agent(subagent_type: "general-purpose", model: "opus", run_in_background: false,
      description: "Implement <thing> per spec",
      prompt: "Implement exactly the spec at <abs path>/spec.md. Work only in
               <repo>. Touch only the files it lists; make no other changes.
               If the spec marks the task as a bug fix, write the regression
               test first, run it, and capture its FAILING output before
               applying the production change. When done, run <test command>
               and report: the exact files you created and the exact files you
               modified (two lists), the failing-then-passing output for a bug
               fix, the test output, and any deviation from the spec and why.")
```

### 3. Spec check (main thread)

Not a formal review stage — you are Fable; just look at the work before handing
it to codex:

- **Scope to the builder's delta — never bare `git diff`** (it mixes in
  pre-existing uncommitted work and misses files the builder *created*). Read
  `git diff -- <modified files>` plus every created file in full. Cross-check
  the builder's lists against `git status --porcelain` vs `baseline.txt` — any
  unlisted change is a stray edit to chase down.
- Check the delta matches the spec's design. For a bug fix, confirm the test
  went red before the fix. Re-run the test command yourself.
- Misses go back to the **same** builder via `SendMessage` (its context is
  intact); repeat until clean. If the builder had to guess, tighten the spec.

### 4. External review (codex-review skill)

Invoke the `codex-review` skill via the Skill tool and follow **its** loop:
pass a session-scope summary built from the builder's file lists, read the
findings, triage them yourself, fix the valid ones, re-review until codex is
clean or nothing new and valid remains. This command is the user's explicit
request for that review — don't ask again.

### 5. E2E verification (when possible and needed)

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

## Guardrails

- **You own correctness.** Codex is a second opinion, not the safety net — the
  spec check in step 3 always happens.
- **Fixes bypass earlier verdicts.** Code changed after codex's last clean
  verdict gets one more codex round (step 5).
- **Stop conditions.** Build loop: delta matches spec, tests green. Codex loop:
  per the codex-review skill. E2E: changed flow works, or skipped with a
  stated reason.
