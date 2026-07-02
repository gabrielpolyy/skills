---
name: codex-implement
description: Have an external implementer (codex exec, workspace-write sandbox) implement a spec you provide, then review the result yourself and loop valid findings back through codex as fix rounds until clean. Use when the user types /codex-implement, or asks for codex to do the implementation ("plan X and then /codex-implement", "have codex build this").
user-invocable: true
---

# Skill: codex-implement

Delegated implementation using the user's `codex` CLI: **you plan and review, codex writes the
code.** You are the architect and the loop controller — you write the spec, hand it to codex,
review what comes back with your own judgment, and send valid findings back through codex as fix
rounds until nothing valid remains. Do not implement the task yourself; the whole point is that
codex produces the code and you hold it to the spec.

Codex runs via `codex exec --sandbox workspace-write`: it can write ONLY inside the repos you
list (plus /tmp), has **no network access**, and is instructed to leave everything uncommitted.
The script fingerprints git refs before/after and prints a `WARNING:` if codex committed or
switched branches anyway, and another `WARNING:` if codex claimed work but changed nothing.

## Steps

1. **Write the spec.** The first argument is the task spec and is **required** — it is the entire
   definition of what codex builds, so never send a vague one-liner. If you just finished planning
   (e.g. the user said "plan X and then /codex-implement"), the approved plan IS the spec. Fold in
   any text the user typed after `/codex-implement`. A good spec names:
   - the goal and the user-visible behavior, including edge cases;
   - the files/areas to touch (and any that must NOT be touched);
   - constraints: API backward compatibility, conventions to follow, things the project's
     CLAUDE.md mandates that codex can't know it cares about;
   - the tests to add or update, and the command that runs them.

   ```bash
   bash ~/.claude/skills/codex-implement/implement.sh "Add a DELETE /api/songs/uploads/:jobId/key-offset endpoint in src/songs/handlers.js: removes the song_options row for (user_id, slug); 404 if none; auth required like the sibling PUT; keep the response shape { ok: true }. Add a regression test next to the PUT's tests in src/songs/handlers.test.js; run 'npm test -- songs' to verify."
   ```

   **Cross-repo tasks.** When the task spans repos (e.g. an API change in one and its consumer in
   another), pass each repo path after the spec — codex gets write access to all of them in one
   call and keeps them consistent. Say in the spec which change lives in which repo.

   ```bash
   bash ~/.claude/skills/codex-implement/implement.sh "In the api repo add field X to /v2/profile (api/src/routes/profile.ts); in the web repo read it in the profile decoder (web/src/api/profile.ts)" ~/code/api ~/code/web
   ```

   - Output `NOT_A_GIT_REPO` → the current dir isn't a git repo (no repo paths were passed).
     Tell the user, stop.
   - Output `CODEX_ERROR: not a git repository: <path>` → fix the path and re-run.
   - Output starting with `CODEX_ERROR:` → relay the error (it includes codex's last log lines)
     and stop; don't loop on a broken call.
   - Exit code 2 / `usage:` → you called it without a spec. Re-run with a real spec.
   - Final message starting with `BLOCKED:` → codex couldn't do the task. Surface the reason to
     the user; either fix the blocker (e.g. install a dependency yourself) and re-run, or stop.
   - A leading `WARNING:` line → read it and act on it (inspect git state / treat the work as not
     done) before trusting the report.

2. **Verify, then review the diff yourself — inline.** Codex's `## Summary` is a claim, not
   evidence. Read the actual uncommitted diff (the script's `working tree` footer shows what was
   touched) and judge it against your spec: correctness and edge cases, matching the surrounding
   code's conventions, no scope creep or drive-by refactors, no broken contracts, tests actually
   added. Run the relevant tests/build yourself even if codex says it ran them. This review is
   yours — do it by reading the diffs directly; do not spawn review skills or subagent reviewers
   for it.

3. **Triage your findings.**
   - **Valid and worth fixing** → collect it for a fix round: file:line, what's wrong, what the
     fix should be.
   - **Not worth it** (style nit, speculative hardening, out-of-scope) → skip, with a one-line
     reason.
   - **Uncertain** whether something is a real problem or worth doing → ask the user before
     spending a round on it.

4. **Fix round.** Batch ALL valid findings into ONE new `implement.sh` call — each call is a real
   codex run (minutes, tokens), so never send findings one at a time. The task argument is a fix
   spec: a one-line recap of the original task, then the numbered findings with file:line and the
   expected fix. The script already tells codex to inspect the uncommitted tree, so it will see
   its own prior work.

   ```bash
   bash ~/.claude/skills/codex-implement/implement.sh "Fix round on the key-offset DELETE endpoint implemented earlier (uncommitted in this tree). Findings: 1) src/songs/handlers.js:214 — missing await on repository call, returns before the row is deleted; 2) handlers.test.js — the 404 case asserts 400. Fix both; run 'npm test -- songs'."
   ```

5. **Decide whether to loop.** Re-review (step 2) after every round. Keep a running list of
   findings you've dismissed so you recognize repeats. **Stop** when ANY of these holds:
   - your review finds no new valid findings AND the relevant tests pass, OR
   - codex has failed to fix the SAME finding two rounds in a row → fix that one yourself
     directly (smallest possible change), note that you did, and finish, OR
   - you've reached the backstop of 10 rounds, OR
   - codex is `BLOCKED` on something only the user can resolve.

6. **Final summary** to the user: how many rounds ran, what got implemented (and by whom, if you
   had to step in), test results, findings fixed, and findings you intentionally skipped with the
   one-line reasons.

## Notes

- **No network, no new dependencies.** The workspace-write sandbox blocks network, and the prompt
  forbids adding dependencies. If the task needs a new package, install it yourself BEFORE the
  codex round and mention in the spec that it's already in node_modules/lockfile.
- Codex leaves all work uncommitted; committing (if the user wants it) happens after the loop,
  by you, on the user's say-so.
- Division of labor with `/codex-review`: this skill's review loop is YOUR inline review. Only
  chain an external `/codex-review` on top if the user explicitly asks for it.
- To test the plumbing without calling codex (prints the prompt that would be sent):
  `CODEX_IMPLEMENT_DRY_RUN=1 bash ~/.claude/skills/codex-implement/implement.sh "test spec"`.
