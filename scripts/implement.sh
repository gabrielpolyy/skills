#!/usr/bin/env bash
# Shared implementation helper for the low/high/scientific workflows: have a
# builder model IMPLEMENT a spec in a repo, with writes confined to that repo.
#
# The inverse of scripts/review.sh: the builder gets WRITE access to the repo
# (codex: --sandbox workspace-write; claude: --permission-mode acceptEdits) so
# it can edit files and run tests, but git history must not move — the prompt
# forbids commits and the script detects them. The spec file's CONTENT is
# embedded into the prompt, so the file itself can live anywhere (e.g. the
# scratchpad) and the builder never depends on reading a path outside the repo.
#
# Before the run, the helper writes a BASELINE SNAPSHOT (HEAD id, status,
# staged/unstaged patches, full contents of untracked files) to a file and
# prints its path first; hand that file to review.sh --baseline so the review
# compares against the pre-task state instead of HEAD.
#
# Usage:  implement.sh <spec-file> [repo]
#           - arg 1 (REQUIRED): existing, non-empty file holding the spec/brief.
#           - arg 2 (optional): repo to work in. Default: the current repo.
# Output: `SNAPSHOT: <path>` first, then the builder's implementation report,
#         or the literal token NOT_A_GIT_REPO, or a line starting with ERROR:.
#         WARNING: lines precede the report when the builder committed or the
#         run changed nothing. `KILLED:` means the helper was stopped by a signal.
# Exit:   0 ok; 1 backend error; 2 usage; 3 report printed but HEAD moved or the
#         working tree did not change; 143 killed by a signal.
# Env:    IMPLEMENT_BACKEND=codex|claude  (default codex) -> which CLI runs the builder.
#         IMPLEMENT_MODEL / IMPLEMENT_EFFORT -> the model and reasoning effort. The
#           values below are DEFAULTS; the workflow overrides them per role.
#         IMPLEMENT_DRY_RUN=1 -> print the recipe and prompt, skip the CLI call.
#         IMPLEMENT_SNAPSHOT=<path> -> where to write the baseline snapshot (default: mktemp).
#           The path may lie inside the repo: the snapshot is collected into a temp
#           file first, moved there afterwards, and excluded from the snapshot itself
#           and from the before/after change detection.

set -uo pipefail

# Model + effort are always passed explicitly. NEVER rely on ~/.codex/config.toml
# or Claude's session defaults — the app model pickers rewrite them, so an
# unpinned run could silently build with a weaker model/effort.
IMPLEMENT_BACKEND="${IMPLEMENT_BACKEND:-codex}"
case "$IMPLEMENT_BACKEND" in
  codex)  : "${IMPLEMENT_MODEL:=gpt-6-astra}"; : "${IMPLEMENT_EFFORT:=medium}" ;;
  claude) : "${IMPLEMENT_MODEL:=fable}";       : "${IMPLEMENT_EFFORT:=high}" ;;
  *) echo "usage: IMPLEMENT_BACKEND must be codex or claude (got '$IMPLEMENT_BACKEND')" >&2; exit 2 ;;
esac

# The spec file is required — it is the entire instruction set for the builder.
# Fail fast on a missing or empty file rather than launching a vague build.
if [ "$#" -lt 1 ] || [ ! -s "${1:-}" ]; then
  echo "usage: implement.sh <spec-file> [repo]" >&2
  echo "  arg 1 must be an existing, non-empty file holding the spec to implement." >&2
  echo "  optional arg 2 is the repo to work in (default: the current repo)." >&2
  exit 2
fi
spec="$(cat -- "$1")" || { echo "ERROR: cannot read spec file: $1"; exit 1; }

# Resolve the repo to work in to its git toplevel — writes are scoped to the
# builder's cwd, so we must run from the repo root.
if [ "$#" -ge 2 ]; then
  root="$(git -C "$2" rev-parse --show-toplevel 2>/dev/null)"
  if [ -z "$root" ]; then echo "ERROR: not a git repository: $2"; exit 1; fi
else
  root="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -z "$root" ]; then echo "NOT_A_GIT_REPO"; exit 0; fi
fi

# sq <text> — single-quote text for a shell example inside the prompt (' -> '\'').
sq() { local q="'" r="'\\''"; printf "'%s'" "${1//$q/$r}"; }

read -r -d '' prompt <<EOF
You are a senior software engineer. Implement EXACTLY the spec at the bottom of this message, in
the repository at $(sq "$root") (your working directory). The spec is the single source of truth: it
was written against the current code and already resolves the design decisions — do not redesign.

Rules:
- Touch ONLY the files the spec lists. No other changes: no drive-by refactors, no reformatting,
  no fixing of unrelated code.
- Add a dependency only when the spec names it, and edit manifest/lock files only as the spec
  requires. If installing it cannot run in this sandbox, say so in your report.
- Match the surrounding code's existing style, naming, and conventions.
- If the spec marks the task as a BUG FIX: write the regression test first, run it, and capture
  its FAILING output BEFORE applying the production change (red-green).
- Run the test command the spec gives and make it pass. If a command cannot run in this sandbox,
  say so in your report instead of claiming success.
- Do NOT change git state: no git add/commit/checkout/restore/stash/reset, no branch changes.
  Leave every change UNCOMMITTED in the working tree — the uncommitted diff is what gets
  reviewed next.
- Writes are allowed only inside this repository (and temp dirs). Do not fetch anything or
  write elsewhere.
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

# The exact CLI recipe per backend. The prompt goes in via stdin, not argv: a
# near-final-code spec can exceed Linux's per-argument size cap, and Git Bash on
# Windows mangles non-ASCII argv when spawning a native exe, while a pipe carries
# raw UTF-8 intact.
#   codex:  --sandbox workspace-write confines writes to the repo (+ temp dirs),
#           blocks network, and -m/-c set the model and effort explicitly.
#   claude: --permission-mode acceptEdits allows file edits inside the project
#           (the equivalent of workspace-write); never bypassPermissions.
recipe() {
  case "$IMPLEMENT_BACKEND" in
    codex)  printf '%s' "codex exec --sandbox workspace-write -m $IMPLEMENT_MODEL -c model_reasoning_effort=$IMPLEMENT_EFFORT -o <tmp> -" ;;
    claude) printf '%s' "claude -p --model $IMPLEMENT_MODEL --effort $IMPLEMENT_EFFORT --permission-mode acceptEdits --no-session-persistence" ;;
  esac
}

if [ "${IMPLEMENT_DRY_RUN:-0}" = "1" ]; then
  # Dry-run previews the recipe and prompt for testing the plumbing without a CLI call.
  echo "DRY_RUN: would run (cwd=${root}; backend=${IMPLEMENT_BACKEND}): $(recipe) <<<\"<prompt below>\""
  echo "----- prompt -----"
  printf '%s\n' "$prompt"
  exit 0
fi

# Where the snapshot ends up. Resolve IMPLEMENT_SNAPSHOT to an absolute path now
# (the script cds into the repo later) and, when it lies inside this repo, note
# its repo-relative path so the snapshot never lists itself and the before/after
# fingerprints ignore it. `git rev-parse --show-prefix` spells the path the way
# git does, so this also works under Git Bash.
snap=""; snap_rel=""
if [ -n "${IMPLEMENT_SNAPSHOT:-}" ]; then
  snap_dir="$(cd "$(dirname "$IMPLEMENT_SNAPSHOT")" 2>/dev/null && pwd -P)" \
    || { echo "ERROR: snapshot directory does not exist: $IMPLEMENT_SNAPSHOT"; exit 1; }
  snap="$snap_dir/$(basename "$IMPLEMENT_SNAPSHOT")"
  if [ "$(git -C "$snap_dir" rev-parse --show-toplevel 2>/dev/null)" = "$root" ]; then
    snap_rel="$(git -C "$snap_dir" rev-parse --show-prefix)$(basename "$IMPLEMENT_SNAPSHOT")"
  fi
fi
# Pathspec that hides the snapshot file from every git command below.
excl=(); [ -n "$snap_rel" ] && excl=(-- . ":(exclude)$snap_rel")

# Baseline material: HEAD id, status, staged/unstaged patches, and the FULL
# contents of every untracked file (the diffs never include those). Hashing the
# whole content — no size cutoff — means a same-size rewrite is still detected.
# review.sh computes the same material, so its --baseline can compare directly.
hash_cmd() { if command -v shasum >/dev/null 2>&1; then shasum; else cksum; fi; }
snapshot_material() {
  printf '### repo: %s\n' "$root"
  printf '### head: %s\n' "$(git -C "$root" rev-parse --verify -q HEAD 2>/dev/null || echo NONE)"
  printf '### status\n'; git -C "$root" status --porcelain ${excl[@]+"${excl[@]}"} 2>/dev/null
  printf '### unstaged\n'; git -C "$root" -c core.pager=cat diff ${excl[@]+"${excl[@]}"} 2>/dev/null          # worktree vs index
  printf '### staged\n';   git -C "$root" -c core.pager=cat diff --cached ${excl[@]+"${excl[@]}"} 2>/dev/null # index vs HEAD/empty tree
  git -C "$root" ls-files --others --exclude-standard -z ${excl[@]+"${excl[@]}"} 2>/dev/null \
    | while IFS= read -r -d '' f; do
        printf '### untracked: %s\n' "$f"; cat -- "$root/$f" 2>/dev/null
      done
}
snapshot() { snapshot_material | hash_cmd | awk '{print $1}'; }

out=""; log=""; child_pid=""
cleanup() { rm -f -- "${out:-}" "${log:-}" 2>/dev/null || true; }
trap cleanup EXIT
# If THIS script is killed (e.g. the caller's timeout fires), take the builder
# down with it — an orphaned builder would keep editing the working tree after
# the caller has already given up on the run. The child runs in its own process
# group when the platform allows (set -m), so its own subprocesses die too.
stop_child() {
  [ -n "$child_pid" ] || return 0
  local pgid mine
  pgid="$(ps -o pgid= -p "$child_pid" 2>/dev/null | tr -d ' ')"
  mine="$(ps -o pgid= -p "$$" 2>/dev/null | tr -d ' ')"
  # Kill the child's whole process group only when it really is a separate group.
  if [ -n "$pgid" ] && [ "$pgid" != "$mine" ]; then kill -- -"$pgid" 2>/dev/null; else kill "$child_pid" 2>/dev/null; fi
  wait "$child_pid" 2>/dev/null
}
on_signal() { stop_child; echo "KILLED: builder stopped by signal; inspect git status"; exit 143; }
trap on_signal TERM INT HUP
out="$(mktemp)"; log="$(mktemp)"

# Run from the repo root: both backends grant write access to the builder's cwd.
cd "$root" || { echo "ERROR: cannot cd to $root"; exit 1; }

# Collect into a temp file first: writing straight to a destination inside the
# repo would let the untracked-file loop read the file it is producing.
snap_tmp="$(mktemp)"
snapshot_material > "$snap_tmp" || { echo "ERROR: cannot write snapshot to $snap_tmp"; rm -f -- "$snap_tmp"; exit 1; }
if [ -n "$snap" ]; then
  mv -f -- "$snap_tmp" "$snap" || { echo "ERROR: cannot write snapshot to $snap"; rm -f -- "$snap_tmp"; exit 1; }
else
  snap="$snap_tmp"
fi
echo "SNAPSHOT: $snap"
before="$(hash_cmd < "$snap" | awk '{print $1}')"
head_before="$(git rev-parse --verify -q HEAD 2>/dev/null || echo NONE)"
set -m 2>/dev/null
case "$IMPLEMENT_BACKEND" in
  codex)
    printf '%s' "$prompt" | codex exec --sandbox workspace-write -m "$IMPLEMENT_MODEL" \
      -c model_reasoning_effort="$IMPLEMENT_EFFORT" -o "$out" - >"$log" 2>&1 &
    ;;
  claude)
    # claude -p prints the final message on stdout; that is the report.
    printf '%s' "$prompt" | claude -p --model "$IMPLEMENT_MODEL" --effort "$IMPLEMENT_EFFORT" \
      --permission-mode acceptEdits --no-session-persistence >"$out" 2>"$log" &
    ;;
esac
child_pid=$!
set +m 2>/dev/null
wait "$child_pid"; rc=$?
child_pid=""
if [ "$rc" -ne 0 ]; then
  echo "ERROR: $IMPLEMENT_BACKEND exited $rc. Last log lines:"
  tail -n 25 "$log"
  exit 1
fi
if [ ! -s "$out" ]; then
  echo "ERROR: $IMPLEMENT_BACKEND produced no final message. Last log lines:"
  tail -n 25 "$log"
  exit 1
fi

status=0
head_after="$(git rev-parse --verify -q HEAD 2>/dev/null || echo NONE)"
if [ "$head_after" != "$head_before" ]; then
  echo "WARNING: HEAD moved during the run — the builder committed (or rewrote history) despite being"
  echo "told not to. Inspect 'git log' and undo the commit (e.g. git reset --soft) before reviewing."
  echo
  status=3
fi
after="$(snapshot)"
if [ "$before" = "$after" ] && [ "$head_after" = "$head_before" ]; then
  echo "WARNING: no working-tree change detected — the implementation may not have happened."
  echo "Read the report below and run 'git status' before assuming any work landed."
  echo
  status=3
fi
cat "$out"
exit "$status"
