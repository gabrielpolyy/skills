#!/usr/bin/env bash
# codex-review helper: have codex review THIS SESSION's changes, read-only.
#
# Codex gathers the diff itself (it has repo read access); this script just
# (a) requires a scope argument, (b) resolves one OR MORE repos to review,
# (c) short-circuits when nothing is uncommitted in any of them, (d) runs codex
# in a hard read-only sandbox, (e) verifies the working trees did not change
# during the review, and (f) prints ONLY codex's final message.
#
# Multiple repos: when a session's changes span repos (e.g. a contract changed in
# one repo and its consumer in another), pass each repo path after the scope so a
# single codex call can review them together and check cross-repo consistency.
# Read-only sandbox grants full-disk READ access, so codex can read every listed
# repo (via `git -C <path>`) while still being unable to write anywhere.
#
# Used by the global `codex-review` skill.
#
# Usage:  review.sh "<session scope: what changed this session and why>" [repo ...]
#           - arg 1 (REQUIRED): the review scope.
#           - args 2..N (optional): repo paths to review. Default: the current repo.
# Output: codex's findings, or the literal token NO_FINDINGS / NO_CHANGES / NOT_A_GIT_REPO,
#         or a line starting with CODEX_ERROR: / WARNING:.
# Env:    CODEX_REVIEW_DRY_RUN=1  -> print the prompt that would be sent, skip the codex call.

set -uo pipefail

# The scope argument is required — it defines what codex reviews. Fail fast on a
# missing or blank scope rather than running a vague review.
if [ "$#" -lt 1 ] || [ -z "${1//[[:space:]]/}" ]; then
  echo "usage: review.sh \"<session scope: what changed this session and why>\" [repo ...]" >&2
  echo "  the scope argument is required; it tells codex which changes to review." >&2
  echo "  optional repo paths after it review cross-repo changes in one pass." >&2
  exit 2
fi
context="$1"; shift
repo_args=("$@")

# Resolve the repos to review to their git toplevels (deduped). With no repo args,
# default to the current repo — keeps the common single-repo invocation unchanged.
repos=()
if [ "${#repo_args[@]}" -eq 0 ]; then
  root="$(git rev-parse --show-toplevel 2>/dev/null)"
  if [ -z "$root" ]; then echo "NOT_A_GIT_REPO"; exit 0; fi
  repos+=("$root")
else
  for p in "${repo_args[@]}"; do
    rt="$(git -C "$p" rev-parse --show-toplevel 2>/dev/null)"
    if [ -z "$rt" ]; then echo "CODEX_ERROR: not a git repository: $p"; exit 1; fi
    dup=0; for e in "${repos[@]:-}"; do [ "$e" = "$rt" ] && { dup=1; break; }; done
    [ "$dup" = 0 ] && repos+=("$rt")
  done
fi
multi=0; [ "${#repos[@]}" -gt 1 ] && multi=1

# Does a repo have a HEAD commit? A fresh repo with no commits has no HEAD, so
# `git diff HEAD` is invalid there and the prompt must steer codex elsewhere.
repo_has_head() { git -C "$1" rev-parse --verify -q HEAD >/dev/null 2>&1; }

# Per-repo instructions for how codex should gather that repo's changes.
gather_block=""
for dir in "${repos[@]}"; do
  if repo_has_head "$dir"; then
    gather_block+="
- Repo '${dir}':
    - git -C '${dir}' diff HEAD        (staged + unstaged changes to tracked files)
    - git -C '${dir}' status --short   then read any new/untracked files it lists — git diff HEAD does NOT include them. Its paths are relative to this repo, so read each as '${dir}/<path>'."
  else
    gather_block+="
- Repo '${dir}' (NO commits yet — HEAD does not exist; do NOT run 'git diff HEAD' here):
    - git -C '${dir}' status --short   and read EVERY file it lists; they are all new this session. Its paths are relative to this repo, so read each as '${dir}/<path>'.
    - git -C '${dir}' diff --cached    to see staged content."
  fi
done

# Cross-repo framing + finding-location hint, only when more than one repo is in scope.
if [ "$multi" = 1 ]; then
  scope_intro="These changes span MULTIPLE repositories (listed under \"Gather the changes\" below). Some
changes are cross-repo: a change in one repo may depend on, or must stay consistent with, a change —
or existing code — in another (e.g. an API/contract/schema/shared-type changed in one repo and its
consumer in another). Review each repo's changes AND their cross-repo consistency. You may read any
file in any of these repos to verify a finding."
  loc_rule=" When more than one repo is under review, prefix each finding's location with the repo it is in, e.g. [severity] <repo-name>/path:line."
else
  scope_intro="Review ONLY those changes; do not review the rest of the repo."
  loc_rule=""
fi

read -r -d '' prompt <<EOF
You are a senior code reviewer. Review the work done in THIS SESSION. The scope is defined by the
"Session scope" section at the bottom — what was changed this session and why.
${scope_intro}

THIS IS A READ-ONLY REVIEW. You must ONLY read and report. Do NOT modify, create, delete, move,
or rename any file. Do NOT write code or apply fixes. Do NOT change git state in any way — no
edits, no git add/commit/checkout/restore/stash/reset, no formatters, no codegen. The only
commands you may run are read-only inspection (git diff, git status, git log, reading files).
Your entire output is a review report, nothing else.

Gather the changes yourself by reading the diffs in each repository below:
${gather_block}
The diff is the source of truth for the code; the Session scope tells you which changes are in
scope and why they were made. If the Session scope describes a change you cannot find in the diffs
(e.g. it was already committed), note that instead of guessing. Do NOT review committed history or
existing code outside this session's changes — except to verify a finding against surrounding or
cross-repo code.

Find real, concrete problems INTRODUCED by this session's changes: correctness bugs, regressions,
broken edge cases, race conditions, security issues, resource leaks, and clear contract
violations. Open any other files you need to verify a finding against the surrounding code. Prefer
a few high-confidence findings over many speculative ones.

Rules:
- Review only. DO NOT modify, create, or delete any files.
- Judge against the actual changes. Do not invent issues or flag pre-existing code the changes don't touch.
- Ignore pure style/formatting/naming nits unless they cause a real bug.
- If there are NO valid, actionable findings, reply with exactly: NO_FINDINGS
- Otherwise list each finding as: [severity] path:line — what's wrong — why — suggested fix. Be concise.${loc_rule}

Session scope — what was changed in this session and why:
${context}
EOF

if [ "${CODEX_REVIEW_DRY_RUN:-0}" = "1" ]; then
  # Dry-run previews the prompt for testing; it deliberately runs BEFORE the
  # no-changes guard so the prompt is shown even in a clean tree.
  echo "DRY_RUN: would run (cwd=${repos[0]}): codex exec --sandbox read-only -o <tmp> \"<prompt below>\""
  echo "----- repos -----"
  printf '%s\n' "${repos[@]}"
  echo "----- prompt -----"
  printf '%s\n' "$prompt"
  exit 0
fi

# Cheap guard: don't spend a codex call when nothing is uncommitted in ANY repo.
any_dirty=0
for dir in "${repos[@]}"; do
  if repo_has_head "$dir"; then
    git -C "$dir" diff --quiet HEAD 2>/dev/null || any_dirty=1
  else
    # No commits yet: "dirty" means something is staged (index vs empty tree).
    git -C "$dir" diff --cached --quiet 2>/dev/null || any_dirty=1
  fi
  [ -n "$(git -C "$dir" ls-files --others --exclude-standard 2>/dev/null)" ] && any_dirty=1
  [ "$any_dirty" = 1 ] && break
done
if [ "$any_dirty" = 0 ]; then
  echo "NO_CHANGES"
  exit 0
fi

# Fingerprint ALL uncommitted state across every repo so we can prove codex changed
# nothing (belt-and-suspenders behind the read-only sandbox): staged + unstaged tracked
# content AND the contents of untracked files. `git diff` / `git diff --cached` are
# HEAD-independent (they diff against the empty tree when there is no commit).
hash_cmd() { if command -v shasum >/dev/null 2>&1; then shasum; else cksum; fi; }
snapshot() {
  {
    for dir in "${repos[@]}"; do
      printf '### repo: %s\n' "$dir"
      git -C "$dir" status --porcelain 2>/dev/null
      git -C "$dir" -c core.pager=cat diff 2>/dev/null          # unstaged: worktree vs index
      git -C "$dir" -c core.pager=cat diff --cached 2>/dev/null # staged: index vs HEAD/empty tree
      # Untracked file contents (the diffs above never include these). Hash content for
      # normal-sized files; for large blobs fall back to name+size to stay fast.
      git -C "$dir" ls-files --others --exclude-standard -z 2>/dev/null \
        | while IFS= read -r -d '' f; do
            full="$dir/$f"
            sz=$(wc -c < "$full" 2>/dev/null || echo 0)
            if [ "${sz:-0}" -gt 1048576 ]; then
              printf '== %s (%s bytes) ==\n' "$f" "$sz"
            else
              printf '== %s ==\n' "$f"; cat -- "$full" 2>/dev/null
            fi
          done
    done
  } | hash_cmd | awk '{print $1}'
}

out=""; log=""
cleanup() { rm -f -- "${out:-}" "${log:-}" 2>/dev/null || true; }
trap cleanup EXIT
out="$(mktemp)"; log="$(mktemp)"

# Run from the first repo so codex's cwd is inside a git repo (it requires one);
# the prompt drives all repos by absolute path via `git -C`.
cd "${repos[0]}" || { echo "CODEX_ERROR: cannot cd to ${repos[0]}"; exit 1; }

before="$(snapshot)"
# --sandbox read-only: codex can read the repos to review, but cannot write, edit,
# or change git state — a hard guarantee, not just a prompt instruction.
# </dev/null: the prompt is passed as an argument, so codex must not also try to read
# stdin — with a non-EOF stdin (e.g. a background/piped invocation) it would block
# "Reading additional input from stdin..." or append unintended input to the prompt.
codex exec --sandbox read-only -o "$out" "$prompt" </dev/null >"$log" 2>&1
rc=$?
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

after="$(snapshot)"
if [ -n "$before" ] && [ "$before" != "$after" ]; then
  echo "WARNING: a working tree changed during the review — codex may have modified files"
  echo "despite the read-only sandbox. Run 'git status' in each repo and inspect before trusting this report."
  echo
fi
cat "$out"
