---
name: codex-implement
description: Delegate an implementation to an external builder — codex exec, in a workspace-write sandbox, implements a self-contained spec in the current repo, runs the tests, and reports back; you then verify the delta yourself. Use when the user types /codex-implement with a task, or asks to have codex implement or build something ("have codex implement this", "let codex build X"). Also the build step of the fable-codex pipeline.
user-invocable: true
---

# Skill: codex-implement

Hand a spec to the user's `codex` CLI and have it do the implementation **in the working
tree**, then verify the result yourself. **You** are the controller — you write the brief,
launch the build, read the report, check the delta, and own the outcome; codex is the builder,
not the owner.

The script runs `codex exec --sandbox workspace-write`: codex can edit files inside the repo
(and temp dirs) and run the tests, but cannot write anywhere else, cannot reach the network,
and is told to leave every change **uncommitted**. The script detects a commit anyway (HEAD
moved) and also warns when the run changed nothing. The spec file's content is embedded into
the prompt, so the file can live outside the repo (scratchpad).

## Steps

1. **Write the brief to a file.** Codex is a one-shot external process: fresh context, no way
   to ask you questions mid-run, no memory across runs. Everything it needs goes in one file
   (scratchpad, e.g. `spec.md`):
   - the files to touch (repo-relative paths) and, for each, exactly what changes — near-final
     code when you have it;
   - the exact test command and what must pass;
   - if it's a bug fix, say so explicitly — the script's prompt then requires red-green
     (the regression test shown failing before the production change);
   - guardrails (match existing style, touch nothing else) and definition of done.

   Don't require anything the sandbox can't do: no network, so no package installs or fetches.

2. **Snapshot the tree** so later verification scopes to codex's delta only (working trees
   often carry unrelated uncommitted work):

   ```bash
   git status --porcelain > <scratchpad>/baseline.txt
   ```

3. **Run the builder.** An Astra/medium build can take several minutes, so pass a generous Bash-tool
   `timeout` (e.g. 600000 ms):

   ```bash
   bash ~/.claude/skills/codex-implement/implement.sh <abs path>/spec.md
   ```

   `implement.sh` lives next to this SKILL.md — adjust the path if the skill is installed
   somewhere other than `~/.claude/skills`. An optional second argument names the repo to work
   in when it isn't the current directory.

   600000 ms is the Bash tool's hard maximum. If a build could plausibly run longer (a large
   spec, many test cycles), run the command with `run_in_background: true` instead and wait for
   its completion notification — a foreground timeout kills the script, and the script then
   kills codex with it, so the build is simply lost.

   - Output `NOT_A_GIT_REPO` → the current dir isn't a git repo and no repo arg was passed.
   - Exit code 2 / `usage:` → the spec-file argument is missing or the file is empty. Write
     the brief first; it's required.
   - Output starting with `CODEX_ERROR:` → relay the error (it includes codex's last log
     lines) and stop; don't loop on a broken call.
   - A leading `WARNING: HEAD moved...` → codex committed despite instructions. Inspect
     `git log`, undo the commit (`git reset --soft <prev>`) so the work is reviewable as an
     uncommitted diff, and surface this to the user.
   - A leading `WARNING: no working-tree change detected` → treat the run as failed until
     proven otherwise: read the report and `git status` before believing anything landed.

4. **Verify — you own the result.** Cross-check `git status --porcelain` against
   `baseline.txt`; read `git diff -- <modified files>` plus every created file in full (never
   bare `git diff` — it mixes in pre-existing uncommitted work). Compare against the report's
   created/modified lists — any unlisted change is a stray edit to chase down. Re-run the test
   command yourself; for a bug fix, confirm the report shows the test failing before the fix.

5. **Fix loop.** Small misses: fix them inline yourself. Substantive misses: write a **new
   self-contained brief** — codex has no memory of the previous run, so restate what exists
   now, what's wrong, and exactly what to change — and re-run step 3. Backstop: after 3 build
   rounds, stop delegating and finish inline.

6. **Report** to the user: what codex built (files + behavior), test status, anything you
   fixed after it, and any spec deviation codex flagged or you accepted.

## Notes

- The script pins the builder to the Astra model at MEDIUM reasoning effort (the exact model id
  lives only at the top of `implement.sh`) for the same reason `codex-review` pins its
  reviewer: the ChatGPT app's model picker rewrites `~/.codex/config.toml`, so an unpinned run
  could silently build with a weaker model. Override via `CODEX_IMPLEMENT_MODEL` /
  `CODEX_IMPLEMENT_EFFORT` only if the user asks.
- The spec goes to codex through stdin, so its size isn't limited by the shell's argument
  cap and non-ASCII text survives on Windows Git Bash.
- Each run is a real external call (costs tokens, takes minutes). Prefer one good brief over
  many small rounds.
- To test the plumbing without calling codex (prints the prompt that would be sent):
  `CODEX_IMPLEMENT_DRY_RUN=1 bash ~/.claude/skills/codex-implement/implement.sh <spec-file>`.
