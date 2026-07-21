---
name: sde
description: Full software-development-engineer pipeline in one command — the main-loop model (Fable) plans and orchestrates, an Opus subagent writes the code, Fable reviews the resulting diff and loops fixes back, then the codex-review skill runs an external second-opinion review and its findings are triaged and fixed until clean. Use when the user types /sde with a task ("do this /sde", "/sde add X"), or asks for the full plan→build→review→codex pipeline in one shot.
user-invocable: true
---

# Skill: sde (plan with Fable, build with Opus, verify with codex)

One command that runs a whole engineering loop with a division of labor:

1. **Plan** — your current (main-loop) model, typically Fable, reads the code and
   writes a near-final spec. All design judgment happens here.
2. **Build** — an **Opus** subagent implements the spec and runs the tests.
3. **Review** — the planner model reads the actual diff, checks it against the
   spec, and loops real findings back to the same subagent until clean.
4. **External review** — invoke the **`codex-review` skill** for an independent
   second opinion, then triage/fix its findings per that skill's own loop.

The planner pays its (higher) rate only for the spec and the reviews; the bulk
typing bills at Opus's rate; codex is a genuinely independent reviewer at the end.

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
    the code, not a description of it.
  - **Tests** — the exact test command (read the project config), the test file to
    extend, and the highest-value regression assertions.
  - **Guardrails** — match existing style; surgical changes only; touch nothing
    outside the listed files; no drive-by refactors.
  - **Definition of done** — tests green, and the specific behaviors that must hold.
- Too small to spec (a one-liner, a rename)? Say so, do it inline, and jump
  straight to step 4.

### 2. Build (Opus subagent)

Launch one subagent with the spec path (it reads the file — keeps the prompt lean).
Keep it synchronous so you can review immediately:

```
Agent(subagent_type: "general-purpose", model: "opus", run_in_background: false,
      description: "Implement <thing> per spec",
      prompt: "Implement exactly the spec at <abs path>/spec.md. Work only in
               <repo>. Touch only the files it lists; make no other changes. When
               done, run <test command> and report: the diff summary, the test
               output, and any point where you deviated from the spec and why.")
```

(If your main loop is already Opus, drop the builder to `model: "sonnet"`.)

### 3. Review (your model, main thread)

- Read the actual diff of every changed file — do not trust the subagent's summary.
- Check it against the spec and for correctness. Review inline yourself — do not
  use the `code-review` skill.
- Re-run the test command yourself to confirm green.
- Real findings → send them back to the **same** subagent with `SendMessage` (its
  context is intact); repeat until the diff is clean or only non-worthwhile nits
  remain. If the builder had to guess, the spec was too thin — tighten the spec,
  don't just accept the guess.

### 4. External review (codex-review skill)

Invoke the `codex-review` skill via the Skill tool and follow **its** steps: pass a
concrete session-scope summary (files touched, what each change does, why), read
codex's findings, triage with your own judgment, fix the valid ones, and re-review
until codex is clean or nothing new and valid remains. `/sde` is the user's
explicit request for this review — don't ask again before running it.

### 5. Report

One final summary: what shipped (files + behavior), test status, what the planner
review changed, what codex flagged and what you fixed vs. skipped (with one-line
reasons), and any spec deviation you accepted.

## Guardrails

- **The planner owns correctness.** Cheaper typing, not cheaper judgment — never
  skip step 3 on the grounds that codex reviews later; codex is a second opinion,
  not the safety net.
- **One repo, real files.** The builder edits the working tree directly. If the
  work needs isolation from parallel edits, add `isolation: "worktree"` to the
  Agent call.
- **Stop conditions.** Build/fix loop: clean diff or only dismissed nits.
  Codex loop: per the codex-review skill (clean, no new valid findings, or its
  round backstop).
