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
   itself — your summary tells it which of those changes are in scope and why. `review.sh`
   lives next to this SKILL.md — adjust the path if the skill is installed somewhere other
   than `~/.claude/skills`. An Astra/medium round can take several minutes, so pass a generous
   Bash-tool `timeout` (e.g. 600000 ms, the tool's maximum) — the default 2 minutes can kill a
   round mid-review. If a round could run longer than that, use `run_in_background: true` and
   wait for the completion notification; a killed script takes codex down with it.

   **Restrict the diff with `--paths` whenever you know the files.** By default codex diffs the
   whole working tree, so any unrelated uncommitted work gets reviewed too, with your summary as
   the only filter. When you know exactly which files this session touched (you usually do; the
   pipelines get the list from `git status --porcelain` vs their baseline), pass them as
   repo-relative paths, whitespace-separated, **before** the scope:

   ```bash
   bash ~/.claude/skills/codex-review/review.sh --paths "src/api/profile.ts src/api/profile.test.ts" "This session: ..."
   ```

   Codex then diffs only those pathspecs and is told everything else is out of scope. Omit
   `--paths` only when the whole uncommitted tree really is this session's work.

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
   - Exit code 2 / `usage:` → you called it without a scope argument (or `--paths` without
     its value). Re-run with a real session-scope summary (it's required; `--paths` comes
     before it, repo paths are optional and come after it).
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

3. **Re-review.** After applying fixes, run the script again to let codex re-check the updated
   changes. Same `--paths` and repos, but **extend the scope text** with two things: what you
   fixed this round, and the findings you dismissed with their one-line reasons, e.g.
   `Already triaged, intentionally not fixed — do not re-raise: (1) ... because ...; (2) ...`.
   The prompt tells codex to skip anything listed there, so rounds stop re-litigating settled
   items and only new problems come back.

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
- The script pins the reviewer to the Astra model at MEDIUM reasoning effort (the exact model id
  lives only at the top of `review.sh`), so the review never depends on whatever model/effort
  `~/.codex/config.toml` currently holds (the ChatGPT app's picker rewrites that file).
  Override via `CODEX_REVIEW_MODEL` / `CODEX_REVIEW_EFFORT` only if the user explicitly asks.
- The prompt goes to codex through stdin, so its size isn't limited by the shell's argument
  cap and non-ASCII text survives on Windows Git Bash.
- To test the plumbing without calling codex (prints the prompt that would be sent):
  `CODEX_REVIEW_DRY_RUN=1 bash ~/.claude/skills/codex-review/review.sh "test scope"`.
  A scope arg is still required; dry-run runs before the no-changes guard, so it previews the
  prompt even in a clean tree.
