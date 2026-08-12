---
name: sde
description: Full software-development-engineer pipeline in one command — the main-loop model plans and orchestrates (a Fable subagent design-reviews the spec when the main loop runs a cheaper model), a cheaper subagent writes the code, Fable reviews the builder's diff and loops fixes back, the codex-review skill runs an external second-opinion review and its findings are triaged and fixed until clean, if the change is user-facing and the project has an e2e harness (e.g. a browser-e2e skill) the changed flow is verified end-to-end in the running app, and a final Fable pass signs off anything that changed after the review. Use when the user types /sde with a task ("do this /sde", "/sde add X"), or asks for the full plan→build→review→codex pipeline in one shot.
user-invocable: true
---

# Skill: sde (plan with Fable, build with Opus, verify with codex)

One command that runs a whole engineering loop with a division of labor:

1. **Plan** — your current (main-loop) model — Fable, or commonly Opus run for
   cost — reads the code and writes a near-final spec. All design judgment
   happens here. If the main loop isn't Fable, the spec then gets a **Fable
   design review** before any code is written (see step 1).
2. **Build** — a cheaper subagent (Opus under a Fable main loop, Sonnet under
   an Opus one) implements the spec, runs the tests, and reports the exact
   files it touched.
3. **Implementation review** — Fable reads the builder's actual delta, checks
   that it respects the proposed design in the spec, and loops real findings
   back to the builder until clean — forced to **Fable** even when the main
   loop runs on another model (see step 3).
4. **External review** — invoke the **`codex-review` skill** for an independent
   second opinion, then triage/fix its findings per that skill's own loop.
5. **E2E verify (when possible and needed)** — if the change is user-facing and
   the project has an e2e harness (e.g. a `browser-e2e` skill), drive the real
   app through the changed flow before reporting done.
6. **Final Fable pass** — if steps 4–5 changed any code after the reviewer's
   last clean verdict, Fable signs off the final state (see step 6).

The bulk typing bills at the builder's (cheaper) rate; design judgment always
crosses Fable at three gates — spec review, implementation review, final pass —
even when the main loop runs cheaper; codex is a genuinely independent reviewer
at the end. When the main loop isn't Fable, all three gates are the **same**
Fable subagent (`sde-reviewer`), continued via `SendMessage` so the spec and
design context are paid for once.

**Requires:** the `codex-review` skill installed (same repo) and the `codex` CLI on
`PATH` for step 4. If either is missing, run steps 1–3 and tell the user step 4 was
skipped and why.

## Workflow

### 1. Plan (your model, main thread)

- The task is whatever the user typed around `/sde`. If it's genuinely ambiguous,
  ask (`AskUserQuestion`) **before** planning — never punt open decisions to the
  builder.
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
- **Fable design review (when your model isn't Fable).** Before launching the
  build, spawn the Fable reviewer (same `Agent(... model: "fable" ...)` call as
  step 3, `name: "sde-reviewer"`, report-only) with a design-review prompt: it
  reads `spec.md` and the code it references, challenges the approach, and
  reports amendments. Fold the real ones into `spec.md`. The build then
  implements a Fable-endorsed design — and steps 3 and 6 continue this **same**
  agent via `SendMessage`, so it never re-reads the spec.
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

(If your main loop is already Opus, drop the builder to `model: "sonnet"`.)

### 3. Implementation review (Fable — forced, even if not your session model)

- **Scope the review to the builder's delta — never bare `git diff`.** Bare
  `git diff` mixes in any pre-existing uncommitted work and omits untracked
  files entirely, so a file the builder *created* would be invisible to it.
  The review input is: `git diff -- <modified files>` for files that existed
  before, plus a full read of every file the builder created. Cross-check the
  builder's two lists against `git status --porcelain` vs `baseline.txt` —
  any file that changed state but isn't on the lists is a stray edit, and
  that's a finding.
- **Force Fable for this review.** If your main-loop model is already Fable,
  review in the main thread as below. If it is anything else (Opus, Sonnet, …),
  do not review with your own model — continue the **same** `sde-reviewer` from
  step 1's design review (`SendMessage` with the delta scope above — it already
  holds the spec), or spawn it now if it doesn't exist yet:

  ```
  Agent(subagent_type: "general-purpose", model: "fable", run_in_background: false,
        name: "sde-reviewer", description: "Review implementation vs design",
        prompt: "Read the spec at <abs path>/spec.md, then read the builder's
                 delta in <repo>: `git diff -- <modified files>`, plus these
                 newly created files in full: <created files>. Review for
                 correctness and for whether the implementation respects the
                 spec's design; report each real finding with file:line and why
                 it matters. Report findings only — change nothing.")
  ```

  You still triage its findings and drive the fix loop from the main thread.
  After the builder applies fixes, send the updated delta back to the **same**
  Fable reviewer (`SendMessage` to `sde-reviewer` — its context is intact) so
  Fable confirms the implementation now respects the design; repeat until it
  reports clean. If the `fable` model is unavailable (the Agent call errors),
  fall back to reviewing inline with your own model and say so in the final
  report.
- Read the actual delta for every file the builder touched — do not trust the
  subagent's summary.
- Check it against the spec and for correctness. Review inline yourself — do not
  use the `code-review` skill.
- For a bug fix, confirm the builder showed the regression test failing before
  the fix; a test that never went red proves nothing.
- Re-run the test command yourself to confirm green.
- Real findings → send them back to the **same** subagent with `SendMessage` (its
  context is intact); repeat until the diff is clean or only non-worthwhile nits
  remain. If the builder had to guess, the spec was too thin — tighten the spec,
  don't just accept the guess.

### 4. External review (codex-review skill)

Invoke the `codex-review` skill via the Skill tool and follow **its** steps: pass a
concrete session-scope summary built from the builder's file lists (files touched,
what each change does, why — not bare `git diff`, for the same reasons as step 3),
read codex's findings, triage, fix the valid ones, and re-review until codex is
clean or nothing new and valid remains. `/sde` is the user's explicit request for
this review — don't ask again before running it.

Triage is design judgment. If your main loop is Fable, triage yourself. If it
isn't, send codex's findings to the same `sde-reviewer` (`SendMessage`) for
accept/reject verdicts and apply the accepted ones — don't substitute your own
judgment for the model that owns correctness.

### 5. E2E verification (when possible and needed)

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
(`subagent_type: "general-purpose"`, the builder's model tier, synchronous) that invokes
the project's e2e skill via the Skill tool and walks the **changed flow
specifically** (not a generic smoke test), exercising the new behavior as the
user would and capturing screenshots if the harness supports them. It reports:
pass/fail per step, what broke, and screenshot paths. Read the verdict and the
key screenshot yourself. If the harness can't run inside a subagent, run it
inline. Anything broken loops back to the **same** builder subagent (as in
step 3), then re-verify.

If either condition fails, skip the step — but say so explicitly in the report
(one line: skipped, and why).

### 6. Final Fable pass (conditional)

Every gate's fixes bypass the gates before it: fixes from the codex loop and
the e2e loop land *after* the reviewer's last clean verdict, so one last gate
must see the final state.

- **Skip** when steps 4–5 changed no code (codex clean, e2e green without
  fixes) — step 3's verdict already covers what ships. Say so in the report.
- **Main loop is Fable:** re-read the consolidated post-review delta yourself.
  If the pipeline ran many fix rounds and your picture of the diff is smeared
  across a long context, prefer a fresh Fable subagent (same pattern as step 3)
  reading spec + consolidated delta with clean eyes.
- **Main loop isn't Fable:** mandatory — `SendMessage` the post-review delta to
  the same `sde-reviewer` for sign-off; loop real findings back to the builder
  and repeat until it reports clean.
- If the post-review fixes were substantial (new logic, not tweaks), also run
  one more codex round on that delta before closing.

### 7. Report

First verify scope: diff `git status --porcelain` against `baseline.txt` one
last time — the changed set must be exactly the spec's files plus fix-loop
additions you approved; anything else is a stray to investigate before
reporting.

Then one final summary: what shipped (files + behavior), test status, what the
planner review changed, what codex flagged and what you fixed vs. skipped (with
one-line reasons), the e2e verification outcome (or why it was skipped), the
final-pass outcome (or why it was skipped), and any spec deviation you accepted.

## Guardrails

- **The planner owns correctness.** Cheaper typing, not cheaper judgment — never
  skip step 3 on the grounds that codex reviews later; codex is a second opinion,
  not the safety net.
- **Fixes bypass earlier gates.** Never close the pipeline on "the diff was
  already reviewed" when code changed after that review — that's what step 6
  exists for.
- **One repo, real files.** The builder edits the working tree directly. If the
  work needs isolation from parallel edits, add `isolation: "worktree"` to the
  Agent call.
- **Stop conditions.** Build/fix loop: clean diff or only dismissed nits.
  Codex loop: per the codex-review skill (clean, no new valid findings, or its
  round backstop). E2E: the changed flow works end-to-end, or the step was
  skipped with a stated reason. Final pass: clean sign-off, or skipped because
  nothing changed post-review.
