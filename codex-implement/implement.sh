#!/usr/bin/env bash
# codex-implement helper: have codex IMPLEMENT a spec in a repo, sandboxed.
#
# The inverse of codex-review/review.sh: codex gets WRITE access to the repo
# (--sandbox workspace-write) so it can edit files and run tests, but the
# boundaries stay hard: writes are confined to the repo (+ temp dirs), network
# is off, and git history must not move — the prompt forbids commits and the
# script detects them. The spec file's CONTENT is embedded into the prompt, so
# the file itself can live anywhere (e.g. the scratchpad) and codex never
# depends on reading a path outside the repo.
#
# Used by the global `codex-implement` skill (and the fable-codex pipeline).
#
# Usage:  implement.sh <spec-file> [repo]
#           - arg 1 (REQUIRED): existing, non-empty file holding the spec/brief.
#           - arg 2 (optional): repo to work in. Default: the current repo.
# Output: codex's implementation report, or the literal token NOT_A_GIT_REPO,
#         or a line starting with CODEX_ERROR: — possibly preceded by WARNING:
#         lines (codex committed / the run changed nothing).
# Env:    CODEX_IMPLEMENT_DRY_RUN=1  -> print the prompt that would be sent, skip the codex call.
#         CODEX_IMPLEMENT_MODEL / CODEX_IMPLEMENT_EFFORT -> override the pinned
#         model/effort (defaults: the two assignments below — the only place the model id lives).

set -uo pipefail

# Pin the builder model + reasoning effort. NEVER rely on ~/.codex/config.toml
# defaults — the ChatGPT app's model picker rewrites them, so an unpinned run
# could silently build with a weaker model/effort.
CODEX_IMPLEMENT_MODEL="${CODEX_IMPLEMENT_MODEL:-gpt-6-astra}"
CODEX_IMPLEMENT_EFFORT="${CODEX_IMPLEMENT_EFFORT:-medium}"

# The spec file is required — it is the entire instruction set for the builder.
# Fail fast on a missing or empty file rather than launching a vague build.
if [ "$#" -lt 1 ] || [ ! -s "${1:-}" ]; then
  echo "usage: implement.sh <spec-file> [repo]" >&2
  echo "  arg 1 must be an existing, non-empty file holding the spec to implement." >&2
  echo "  optional arg 2 is the repo to work in (default: the current repo)." >&2
  exit 2
fi
spec="$(cat -- "$1")" || { echo "CODEX_ERROR: cannot read spec file: $1"; exit 1; }

# Resolve the repo to work in to its git toplevel — workspace-write scopes
# writes to codex's cwd, so we must run from the repo root.
if [ "$#" -ge 2 ]; then
  root="$(git -C "$2" rev-parse --show-toplevel 2>/dev/null)"
  if [ -z "$root" ]; then echo "CODEX_ERROR: not a git repository: $2"; exit 1; fi
else
  root="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -z "$root" ]; then echo "NOT_A_GIT_REPO"; exit 0; fi
fi

read -r -d '' prompt <<EOF
You are a senior software engineer. Implement EXACTLY the spec at the bottom of this message, in
the repository at '${root}' (your working directory). The spec is the single source of truth: it
was written against the current code and already resolves the design decisions — do not redesign.

Rules:
- Touch ONLY the files the spec lists. No other changes: no drive-by refactors, no reformatting,
  no fixing of unrelated code, no new dependencies.
- Match the surrounding code's existing style, naming, and conventions.
- If the spec marks the task as a BUG FIX: write the regression test first, run it, and capture
  its FAILING output BEFORE applying the production change (red-green).
- Run the test command the spec gives and make it pass. If a command cannot run in this sandbox,
  say so in your report instead of claiming success.
- Do NOT change git state: no git add/commit/checkout/restore/stash/reset, no branch changes.
  Leave every change UNCOMMITTED in the working tree — the uncommitted diff is what gets
  reviewed next.
- The sandbox allows writes only inside this repository (and temp dirs) and blocks network
  access. Do not try to install packages or fetch anything.
- If part of the spec is impossible, contradictory, or clearly wrong against the real code,
  implement the rest, keep any deviation minimal, and flag it in your report. Do not silently
  invent a different design.

Your final message must be an implementation report, nothing else:
1. Files created and files modified — two exact lists.
2. For a bug fix: the failing-then-passing test output.
3. The test command(s) you ran and their final result.
4. Any deviation from the spec, with the reason.

Spec:
${spec}
EOF

if [ "${CODEX_IMPLEMENT_DRY_RUN:-0}" = "1" ]; then
  # Dry-run previews the prompt for testing the plumbing without a codex call.
  echo "DRY_RUN: would run (cwd=${root}): codex exec --sandbox workspace-write -m $CODEX_IMPLEMENT_MODEL -c model_reasoning_effort=$CODEX_IMPLEMENT_EFFORT -o <tmp> - <<<\"<prompt below>\""
  echo "----- prompt -----"
  printf '%s\n' "$prompt"
  exit 0
fi

# Fingerprint all uncommitted state (status + staged/unstaged diffs + untracked
# file contents) so we can tell whether the run actually changed anything.
hash_cmd() { if command -v shasum >/dev/null 2>&1; then shasum; else cksum; fi; }
snapshot() {
  {
    git -C "$root" status --porcelain 2>/dev/null
    git -C "$root" -c core.pager=cat diff 2>/dev/null          # unstaged: worktree vs index
    git -C "$root" -c core.pager=cat diff --cached 2>/dev/null # staged: index vs HEAD/empty tree
    # Untracked file contents (the diffs above never include these). Hash content
    # for normal-sized files; for large blobs fall back to name+size to stay fast.
    git -C "$root" ls-files --others --exclude-standard -z 2>/dev/null \
      | while IFS= read -r -d '' f; do
          full="$root/$f"
          sz=$(wc -c < "$full" 2>/dev/null || echo 0)
          if [ "${sz:-0}" -gt 1048576 ]; then
            printf '== %s (%s bytes) ==\n' "$f" "$sz"
          else
            printf '== %s ==\n' "$f"; cat -- "$full" 2>/dev/null
          fi
        done
  } | hash_cmd | awk '{print $1}'
}

out=""; log=""; codex_pid=""
cleanup() { rm -f -- "${out:-}" "${log:-}" 2>/dev/null || true; }
trap cleanup EXIT
# If THIS script is killed (e.g. the caller's timeout fires), take codex down with
# it — an orphaned builder would keep editing the working tree after the caller
# has already given up on the run.
on_signal() { [ -n "$codex_pid" ] && kill "$codex_pid" 2>/dev/null; exit 143; }
trap on_signal TERM INT HUP
out="$(mktemp)"; log="$(mktemp)"

# Run from the repo root: workspace-write grants write access to codex's cwd.
cd "$root" || { echo "CODEX_ERROR: cannot cd to $root"; exit 1; }

before="$(snapshot)"
head_before="$(git rev-parse --verify -q HEAD 2>/dev/null || echo NONE)"
# --sandbox workspace-write: codex can edit files in this repo and run the tests,
# but cannot write outside it, reach the network, or (per the prompt) commit.
# -m/-c pin the builder to Astra at MEDIUM reasoning effort — see the note above.
# The prompt goes in via stdin (`-`), not argv: a near-final-code spec can exceed
# Linux's per-argument size cap, and Git Bash on Windows mangles non-ASCII argv
# when spawning a native exe, while a pipe carries raw UTF-8 intact.
printf '%s' "$prompt" | codex exec --sandbox workspace-write -m "$CODEX_IMPLEMENT_MODEL" \
  -c model_reasoning_effort="$CODEX_IMPLEMENT_EFFORT" -o "$out" - >"$log" 2>&1 &
codex_pid=$!
wait "$codex_pid"; rc=$?
codex_pid=""
if [ "$rc" -ne 0 ]; then
  echo "CODEX_ERROR: codex exec exited $rc. Last log lines:"
  tail -n 25 "$log"
  exit 1
fi
if [ ! -s "$out" ]; then
  echo "CODEX_ERROR: codex produced no final message. Last log lines:"
  tail -n 25 "$log"
  exit 1
fi

head_after="$(git rev-parse --verify -q HEAD 2>/dev/null || echo NONE)"
if [ "$head_after" != "$head_before" ]; then
  echo "WARNING: HEAD moved during the run — codex committed (or rewrote history) despite being"
  echo "told not to. Inspect 'git log' and undo the commit (e.g. git reset --soft) before reviewing."
  echo
fi
after="$(snapshot)"
if [ "$before" = "$after" ] && [ "$head_after" = "$head_before" ]; then
  echo "WARNING: no working-tree change detected — the implementation may not have happened."
  echo "Read the report below and run 'git status' before assuming any work landed."
  echo
fi
cat "$out"
