---
name: sde-opus-sol
description: Software-development-engineer pipeline without Fable — Opus does the thinking, codex (Sol) does the reviewing. The main-loop model plans and writes a near-final spec (an Opus subagent design-reviews it when the main loop runs cheaper than Opus), an Opus subagent implements it, the planner checks the builder's delta against the spec on Opus, the codex-review skill (pinned to Sol at high reasoning effort) runs the pipeline's code review and its findings are triaged and fixed until clean, if the change is user-facing and the project has an e2e harness (e.g. a browser-e2e skill) an Opus subagent verifies the changed flow in the running app, and a final codex round signs off anything that changed after codex's last clean verdict. Use when the user types /sde-opus-sol with a task ("do this /sde-opus-sol", "/sde-opus-sol add X"), or asks for the sde pipeline on Opus and codex only (no Fable).
user-invocable: true
---

# Skill: sde-opus-sol (plan and build with Opus, review with Sol)

The `sde` engineering loop on a fixed model budget: **Opus and codex's Sol
model only — Fable is never spawned.** ("Sol" is the reviewer the
`codex-review` skill pins: `gpt-5.6-sol` at high reasoning effort.)

1. **Plan** — the main-loop model reads the code and writes a near-final spec.
   All design judgment happens here. If the main loop runs cheaper than Opus,
   the spec gets an **Opus design review** before any code is written (see
   step 1).
2. **Build** — an Opus subagent implements the spec, runs the tests, and
   reports the exact files it touched.
3. **Implementation check** — the planner reads the builder's actual delta,
   checks that it respects the proposed design in the spec, and loops real
   findings back to the builder until clean. This runs on Opus or better: the
   main thread when your model is Opus or better, otherwise the same Opus
   reviewer subagent (see step 3).
4. **Code review** — the **`codex-review` skill** is this pipeline's code
   reviewer — not a second opinion, *the* review. Triage and fix its findings
   per that skill's own loop until codex is clean.
5. **E2E verify (when possible and needed)** — if the change is user-facing and
   the project has an e2e harness (e.g. a `browser-e2e` skill), an **Opus**
   subagent drives the real app through the changed flow before reporting done.
6. **Final codex round** — if step 5 changed any code after codex's last clean
   verdict, one more codex round covers the final state (see step 6).

Division of labor: Opus owns design, code, and product verification; codex
(Sol) owns the code review. Where `sde` routes design judgment through Fable
gates, this pipeline never escalates above Opus — the independent quality gate
is codex. When the main loop runs cheaper than Opus, all Opus gates — spec
review, implementation check, triage verdicts, final sign-off — are the
**same** Opus subagent (`sde-opus-reviewer`), continued via `SendMessage` so
the spec and design context are paid for once.

**Requires:** the `codex-review` skill installed (same repo) and the `codex`
CLI on `PATH`. Codex is the only code reviewer here — if either is missing,
stop after step 3, tell the user the review gate could not run, and suggest
installing codex or running `/sde` instead. Never present the result as
"reviewed" without it.

## Workflow

### 1. Plan (your model, main thread)

- The task is whatever the user typed around `/sde-opus-sol`. If it's genuinely
  ambiguous, ask (`AskUserQuestion`) **before** planning — never punt open
  decisions to the builder.
- Read the relevant code yourself and resolve the real design decisions.
- Write a **near-final spec** to the scratchpad dir as `spec.md`. It must be
  self-contained — the builder should not need to rediscover anything:
  - **Exact files** to touch (absolute paths) and, for each, exactly what changes.
  - **Near-final code** — signatures, actual logic/SQL, wiring. Give the builder
    the code, not a description of it. Exception — large mechanical changes (the
    same pattern across many files, bulk renames/translations), where writing
    near-final code costs as much as building: spec those at design level
    instead — interfaces, invariants, one worked example, exact test cases —
    and lean on step 3 as the quality gate.
  - **Tests** — the exact test command (read the project config), the test file to
    extend, and the highest-value regression assertions. If the task is a bug
    fix, mark it as one in the spec and require red-green: the regression test
    must be shown failing before the production change is applied.
  - **Guardrails** — match existing style; surgical changes only; touch nothing
    outside the listed files; no drive-by refactors.
  - **Definition of done** — tests green, and the specific behaviors that must hold.
- **Opus design review (when your model is cheaper than Opus).** Before
  launching the build, spawn the Opus reviewer (same
  `Agent(... model: "opus" ...)` call as step 3, `name: "sde-opus-reviewer"`,
  report-only) with a design-review prompt: it reads `spec.md` and the code it
  references, challenges the approach, and reports amendments. Fold the real
  ones into `spec.md`. The build then implements an Opus-endorsed design — and
  steps 3, 4, and 6 continue this **same** agent via `SendMessage`, so it never
  re-reads the spec. If your model is Opus or better, skip this — your own
  planning judgment is the design gate, and this pipeline never spawns
  anything above Opus.
- Too small to spec (a one-liner, a rename)? Say so, do it inline, and jump
  straight to step 4.

### 2. Build (Opus subagent)

First snapshot the tree — working trees often carry unrelated uncommitted work,
and every later step must be scoped to the builder's changes only:

```
git status --porcelain > <scratchpad>/baseline.txt
```

Then launch one subagent with the spec path (it reads the file — keeps the prompt
lean). Keep it synchronous so you can review immediately:

```
Agent(subagent_type: "general-purpose", model: "opus", run_in_background: false,
      description: "Implement <thing> per spec",
      prompt: "Implement exactly the spec at <abs path>/spec.md. Work only in
               <repo>. Touch only the files it lists; make no other changes.
               If the spec marks the task as a bug fix, write the regression
               test first, run it, and capture its FAILING output before
               applying the production change. When done, run <test command>
               and report: the exact files you created and the exact files you
               modified (two lists), the failing-then-passing test output for
               a bug fix, the test output, and any point where you deviated
               from the spec and why.")
```

The builder is always `model: "opus"` — even when your main loop is Opus. A
separate builder context keeps the planner's context clean for review.

### 3. Implementation check (Opus or better)

- **Scope the review to the builder's delta — never bare `git diff`.** Bare
  `git diff` mixes in any pre-existing uncommitted work and omits untracked
  files entirely, so a file the builder *created* would be invisible to it.
  The review input is: `git diff -- <modified files>` for files that existed
  before, plus a full read of every file the builder created. Cross-check the
  builder's two lists against `git status --porcelain` vs `baseline.txt` —
  any file that changed state but isn't on the lists is a stray edit, and
  that's a finding.
- **Route by your model — never spawn Fable.** If your main-loop model is Opus
  or better, review in the main thread as below. If it is cheaper (Sonnet,
  Haiku, …), do not review with your own model — continue the **same**
  `sde-opus-reviewer` from step 1's design review (`SendMessage` with the
  delta scope above — it already holds the spec), or spawn it now if it
  doesn't exist yet:

  ```
  Agent(subagent_type: "general-purpose", model: "opus", run_in_background: false,
        name: "sde-opus-reviewer", description: "Review implementation vs design",
        prompt: "Read the spec at <abs path>/spec.md, then read the builder's
                 delta in <repo>: `git diff -- <modified files>`, plus these
                 newly created files in full: <created files>. Review for
                 correctness and for whether the implementation respects the
                 spec's design; report each real finding with file:line and why
                 it matters. Report findings only — change nothing.")
  ```

  You still triage its findings and drive the fix loop from the main thread.
  After the builder applies fixes, send the updated delta back to the **same**
  Opus reviewer (`SendMessage` to `sde-opus-reviewer` — its context is intact)
  so it confirms the implementation now respects the design; repeat until it
  reports clean.
- Read the actual delta for every file the builder touched — do not trust the
  subagent's summary.
- Check it against the spec and for correctness. Review inline yourself — do not
  use the `code-review` skill.
- For a bug fix, confirm the builder showed the regression test failing before
  the fix; a test that never went red proves nothing.
- Re-run the test command yourself to confirm green.
- Real findings → send them back to the **same** builder subagent with
  `SendMessage` (its context is intact); repeat until the diff is clean or only
  non-worthwhile nits remain. If the builder had to guess, the spec was too
  thin — tighten the spec, don't just accept the guess.

### 4. Code review (codex-review skill — the pipeline's reviewer)

Invoke the `codex-review` skill via the Skill tool and follow **its** steps: pass a
concrete session-scope summary built from the builder's file lists (files touched,
what each change does, why — not bare `git diff`, for the same reasons as step 3),
read codex's findings, triage, fix the valid ones, and re-review until codex is
clean or nothing new and valid remains. `/sde-opus-sol` is the user's explicit
request for this review — don't ask again before running it.

This is the pipeline's only code review, so don't soft-pedal the loop: run it
to a genuine stop condition (clean, no new valid findings, or the skill's round
backstop), never "one round was probably enough".

Triage is design judgment. If your main loop is Opus or better, triage
yourself. If it isn't, send codex's findings to the same `sde-opus-reviewer`
(`SendMessage`) for accept/reject verdicts and apply the accepted ones — don't
substitute your own judgment for the model that owns correctness.

### 5. E2E verification (Opus subagent, when possible and needed)

Unit tests and reviews check the code; this step checks the product. Run it only
when **both** hold:

- **Needed** — the change affects behavior a user actually reaches (UI, routes,
  flows, rendered output). Skip for pure refactors, test-only, doc, or internal
  tooling changes.
- **Possible** — the project has a real way to drive the running app: a project
  e2e skill (e.g. `browser-e2e`), a `run`-style skill, or a documented dev-server
  + browser-automation path. Don't build an e2e harness from scratch just for
  this — that's its own task.

If both hold, delegate the drive — browser turns and screenshots are mechanical
volume that shouldn't fill the planner's context. Launch a subagent
(`subagent_type: "general-purpose"`, `model: "opus"`, synchronous) that invokes
the project's e2e skill via the Skill tool and walks the **changed flow
specifically** (not a generic smoke test), exercising the new behavior as the
user would and capturing screenshots if the harness supports them. It reports:
pass/fail per step, what broke, and screenshot paths. Read the verdict and the
key screenshot yourself. If the harness can't run inside a subagent, run it
inline. Anything broken loops back to the **same** builder subagent (as in
step 3), then re-verify.

If either condition fails, skip the step — but say so explicitly in the report
(one line: skipped, and why).

### 6. Final codex round (conditional)

The codex loop re-reviews its own fixes until clean, so after step 4 the
reviewed state and the shipped state match. Only step 5's fixes can land after
that verdict — and they must not ship unreviewed.

- **Skip** when step 5 changed no code (or was skipped) — codex's last clean
  verdict already covers what ships. Say so in the report.
- Otherwise: re-run the codex-review loop scoped to the e2e fixes (name the
  files and what changed; note the rest of the delta was already reviewed
  clean), re-run the test command, and read the fix delta yourself. If your
  main loop is cheaper than Opus, also `SendMessage` that delta to the same
  `sde-opus-reviewer` for design sign-off; loop real findings back to the
  builder and repeat until clean.

### 7. Report

First verify scope: diff `git status --porcelain` against `baseline.txt` one
last time — the changed set must be exactly the spec's files plus fix-loop
additions you approved; anything else is a stray to investigate before
reporting.

Then one final summary: what shipped (files + behavior), test status, what the
implementation check changed, what codex flagged and what you fixed vs. skipped
(with one-line reasons), the e2e verification outcome (or why it was skipped),
the final codex round's outcome (or why it was skipped), and any spec deviation
you accepted.

## Guardrails

- **No Fable.** This pipeline never spawns a subagent above Opus; the
  independent quality gate is codex. If the user wants Fable gates, that's
  `/sde`.
- **The planner owns correctness.** Codex reviews the code, but never skip
  step 3 on the grounds that codex reviews later — an unread diff never ships,
  and the planner is who checks the build against the design.
- **Fixes bypass earlier gates.** Never close the pipeline on "the diff was
  already reviewed" when code changed after codex's last clean verdict —
  that's what step 6 exists for.
- **One repo, real files.** The builder edits the working tree directly. If the
  work needs isolation from parallel edits, add `isolation: "worktree"` to the
  Agent call.
- **Stop conditions.** Build/fix loop: clean diff or only dismissed nits.
  Codex loop: per the codex-review skill (clean, no new valid findings, or its
  round backstop). E2E: the changed flow works end-to-end, or the step was
  skipped with a stated reason. Final round: codex clean on the e2e fixes, or
  skipped because nothing changed post-review.
