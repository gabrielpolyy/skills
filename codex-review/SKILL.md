---
name: codex-review
description: Have an external reviewer (codex exec, read-only sandbox) review what changed in this session, then triage and fix the valid findings, iterating until codex is clean or the only remaining findings aren't valid/necessary. Use when the user types /codex-review, or asks to have the current changes reviewed by codex — typically right after implementing or fixing something ("implement this then /codex-review").
user-invocable: true
---

# Skill: codex-review

Second-opinion code review of **what landed in this session** using the user's `codex` CLI,
then act on the findings with judgment. This runs at the end of a session, so the scope is the
session's result — the changes you made. **You** are the loop controller — you define the scope,
read findings, decide, fix, and re-review.

Codex gathers the diff itself (it has repo read access and runs `git diff`/`git status`);
the script just short-circuits when nothing is uncommitted and captures codex's final verdict
cleanly. **The review is strictly read-only by enforcement, not just instruction:** the script
runs `codex exec --sandbox read-only`, so codex physically cannot write, edit, or change git
state — and it also fingerprints all uncommitted state (staged + unstaged tracked content AND
untracked file contents) before/after and prints a `WARNING:` line if anything changed.
(`codex exec` is non-interactive, so the read-only sandbox never hangs on an approval prompt.)
The prompt also forbids edits as a second layer.

## Steps

1. **Run the reviewer, telling it what landed.** The first argument is the review **scope** and is
   **required** — never run it empty or vague. You did the work this session, so spell it out
   concretely: the files/areas touched, what each change does, and why (root cause for a fix).
   This is what tells codex which changes to focus on. Fold in any text the user typed after
   `/codex-review`.

   ```bash
   bash ~/.claude/skills/codex-review/review.sh "This session: fixed empty-WAV take mixing in HighwayTakeMixer.swift (root cause: tap-vs-file format mismatch on Bluetooth in AudioManager.swift); split voice/instrumental load errors; added regression tests in HighwayTakeTimelineTests.swift"
   ```

   The script runs from anywhere (it cd's to the repo root) and codex diffs the working tree
   itself — your summary tells it which of those changes are in scope and why.

   **Cross-repo changes.** When this session's work spans more than one repo (e.g. you changed an
   API/contract/shared type in one repo and its consumer in another), pass each repo path as an
   extra argument after the scope. A single codex call then reviews them together and can check
   cross-repo consistency (the read-only sandbox still grants full read access to each repo).
   Decide based on where you actually made changes this session — if it was one repo, pass none
   (defaults to the current repo); if it was several, list them all. In your scope summary, say
   which change lives in which repo so codex can connect them.

   ```bash
   bash ~/.claude/skills/codex-review/review.sh "This session: renamed the /v2/profile response field user_id→id in the api repo (api/src/routes/profile.ts) and updated the web client decoder to match (web/src/api/profile.ts); added a contract test in api" ~/code/api ~/code/web
   ```

   - Output `NO_CHANGES` → nothing is uncommitted to review in any of the repos. Tell the user, stop.
   - Output `NOT_A_GIT_REPO` → the current dir isn't a git repo (no repo paths were passed). Tell
     the user, stop.
   - Output `CODEX_ERROR: not a git repository: <path>` → a repo path you passed isn't a git repo.
     Fix the path and re-run (don't drop the repo silently if its changes are in scope).
   - Output starting with `CODEX_ERROR:` → relay the error (it includes codex's last log
     lines) and stop; don't loop on a broken call.
   - Exit code 2 / `usage:` → you called it without a scope argument. Re-run with a real
     session-scope summary (it's required; repo paths are optional and come after it).
   - A leading `WARNING:` line → a working tree changed during the review (codex shouldn't
     be able to write under the read-only sandbox). Surface it, run `git status` in each repo,
     and have the user verify before trusting the report.

2. **Read codex's output and triage** each finding with your own judgment — codex is a
   second opinion, not an authority:

   - **Valid and worth fixing** → fix it. Make the smallest change that follows the
     surrounding code's conventions. Per the repo's CLAUDE.md, for a genuine bug fix add or
     update the smallest focused regression test, then run the relevant test(s)/build.
   - **Invalid, wrong, or not applicable** (codex misread the code, flagged pre-existing
     code, or is speculating) → skip it. Note in one line why you're skipping.
   - **Not necessary** (technically true but not worth the churn — speculative hardening,
     style nit, out-of-scope refactor) → skip it, with a one-line reason.
   - **Uncertain** whether a finding is valid or worth doing → ask the user (a short
     question, or AskUserQuestion) before acting. Don't guess on judgment calls.

3. **Re-review.** After applying fixes, run the script again (same command) to let codex
   re-check the updated changes.

4. **Decide whether to loop.** Always evaluate the round's output before re-running. Keep a short
   running list of findings you've dismissed (and why) so you can recognize repeats across rounds.
   **Stop** when ANY of these holds — otherwise fix the new valid findings and re-review:
   - codex returns `NO_FINDINGS` (clean), OR
   - the round surfaced **no new valid findings** — everything it raised is either already fixed,
     or matches something you judged invalid/unnecessary in a PREVIOUS round. Codex re-surfacing
     items you already dismissed is the signal to stop, not to re-litigate them, OR
   - you've reached the backstop of 10 rounds.

   Only a NEW, valid finding justifies another fix-and-re-review cycle.

5. **Final summary** to the user: how many rounds ran, what you fixed, what you intentionally
   skipped (with the one-line reasons), and codex's final verdict.

## Notes

- Scope is uncommitted work (tracked changes vs HEAD + new untracked files); codex diffs it
  itself. No commit is required. With multiple repos this is the union across all of them, and
  `NO_CHANGES` only fires when every listed repo is clean.
- Each codex round is a real external call (costs tokens, takes ~1–several minutes). That's
  why this is manual, not a hook — invoke it when you actually want the review.
- To test the plumbing without calling codex (prints the prompt that would be sent):
  `CODEX_REVIEW_DRY_RUN=1 bash ~/.claude/skills/codex-review/review.sh "test scope"`.
  A scope arg is still required; dry-run runs before the no-changes guard, so it previews the
  prompt even in a clean tree.
