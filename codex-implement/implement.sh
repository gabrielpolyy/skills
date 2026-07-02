#!/usr/bin/env bash
# codex-implement helper: have codex IMPLEMENT a specified task in the workspace.
#
# The caller (Claude) is the architect and reviewer; codex is the implementer.
# This script (a) requires a task-spec argument, (b) resolves one OR MORE repos
# codex may write to, (c) runs codex in a workspace-write sandbox (write access
# limited to those repos + /tmp; NO network), (d) verifies codex didn't commit
# or move HEAD, (e) prints codex's final message plus a changed-files footer so
# the caller can immediately see what was touched.
#
# Multiple repos: when a task spans repos (e.g. change an API in one repo and its
# consumer in another), pass each repo path after the spec. The first repo is the
# primary workspace (codex's cwd); the rest are added as writable dirs.
#
# Used by the global `codex-implement` skill.
#
# Usage:  implement.sh "<task spec: what to implement, files, constraints, tests>" [repo ...]
#           - arg 1 (REQUIRED): the task spec (or fix-round findings).
#           - args 2..N (optional): repo paths codex may write to. Default: the current repo.
# Output: codex's final message + a `----- working tree -----` footer,
#         or the literal token NOT_A_GIT_REPO,
#         or a line starting with CODEX_ERROR: / WARNING:.
# Env:    CODEX_IMPLEMENT_DRY_RUN=1 -> print the prompt that would be sent, skip the codex call.

set -uo pipefail

# The task spec is required — it is the entire definition of what codex builds.
# Fail fast on a missing or blank spec rather than letting codex freestyle.
if [ "$#" -lt 1 ] || [ -z "${1//[[:space:]]/}" ]; then
  echo "usage: implement.sh \"<task spec: what to implement, files, constraints, tests>\" [repo ...]" >&2
  echo "  the task-spec argument is required; it tells codex exactly what to implement." >&2
  echo "  optional repo paths after it grant write access for cross-repo tasks." >&2
  exit 2
fi
task="$1"; shift
repo_args=("$@")

# Resolve the repos codex may write to, as git toplevels (deduped). With no repo
# args, default to the current repo — the common single-repo invocation.
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

# Per-repo instructions for inspecting the CURRENT uncommitted state before coding.
# Matters on fix rounds (the prior round's work is sitting uncommitted in the tree)
# and whenever the session already dirtied the tree before delegating to codex.
state_block=""
for dir in "${repos[@]}"; do
  if repo_has_head "$dir"; then
    state_block+="
- Repo '${dir}':
    - git -C '${dir}' diff HEAD        (uncommitted changes to tracked files, if any)
    - git -C '${dir}' status --short   then read any new/untracked files it lists — they may be part of the in-progress work. Its paths are relative to this repo, so read each as '${dir}/<path>'."
  else
    state_block+="
- Repo '${dir}' (NO commits yet — HEAD does not exist; do NOT run 'git diff HEAD' here):
    - git -C '${dir}' status --short   and read the files it lists; everything in this repo is new.
    - git -C '${dir}' diff --cached    to see staged content."
  fi
done

if [ "$multi" = 1 ]; then
  scope_intro="This task spans MULTIPLE repositories (listed under \"Repositories\" below). You have write
access to all of them; a change in one repo may need a matching change in another (e.g. an
API/contract/schema/shared type and its consumer). Keep the repos consistent with each other. In
your summary, prefix each file with the repo it is in."
else
  scope_intro="Work ONLY inside this repository."
fi

read -r -d '' prompt <<EOF
You are a senior software engineer. IMPLEMENT the task defined in the "Task spec" section at the
bottom. ${scope_intro}

Repositories you may write to (and nowhere else):
$(printf -- '- %s\n' "${repos[@]}")

Before writing code, inspect the current state — the task may build on uncommitted work already in
the tree (e.g. a fix round on a prior implementation):
${state_block}

Implementation rules:
- Implement exactly what the spec asks — no extra features, no speculative abstractions or
  configurability, no drive-by refactors or cleanup of code the task doesn't require touching.
- Match the surrounding code's existing conventions, style, naming, and idioms, even where you
  would personally do it differently.
- Keep the diff minimal: every changed line should trace directly to the spec.
- Add or update the focused tests the spec calls for. If the repo has an obvious, cheap test
  command, run the narrowest relevant tests and report the results. You have NO network access —
  never try to install dependencies or fetch anything.
- Do NOT add new dependencies. If part of the task truly requires one, leave that part undone and
  say so in the summary.
- Leave ALL work uncommitted. Do NOT run git commit, push, branch, checkout, switch, merge,
  rebase, reset, or stash — change files only; the caller reviews the working tree.
- If part of the spec is ambiguous, pick the reading most consistent with the surrounding code and
  record it under "Deviations / assumptions" — do not silently expand scope.

End with a final message in exactly this shape:
## Summary
- What you implemented, briefly.
- Files changed: each file with a one-line note on what changed in it.
- Tests: the command(s) you ran and the results, or why you couldn't run any.
- Deviations / assumptions: anything done differently from the spec, or ambiguities you resolved.
- Left undone: anything you could not complete, and why. Write "nothing" if complete.

If you cannot implement the task at all, make your final message a single paragraph starting with
BLOCKED: followed by the reason.

Task spec:
${task}
EOF

# Extra repos become additional writable dirs; the first repo is the primary
# workspace by virtue of being codex's cwd.
add_dir_args=()
for dir in "${repos[@]:1}"; do add_dir_args+=(--add-dir "$dir"); done

if [ "${CODEX_IMPLEMENT_DRY_RUN:-0}" = "1" ]; then
  echo "DRY_RUN: would run (cwd=${repos[0]}): codex exec --sandbox workspace-write ${add_dir_args[*]:-} -o <tmp> \"<prompt below>\""
  echo "----- repos -----"
  printf '%s\n' "${repos[@]}"
  echo "----- prompt -----"
  printf '%s\n' "$prompt"
  exit 0
fi

# Fingerprint git refs so we can prove codex only touched files: HEAD + current
# branch per repo. The prompt forbids commits; this catches it if one slips through.
ref_snapshot() {
  for dir in "${repos[@]}"; do
    printf '%s %s %s\n' "$dir" \
      "$(git -C "$dir" rev-parse -q --verify HEAD 2>/dev/null || echo NO_HEAD)" \
      "$(git -C "$dir" symbolic-ref -q HEAD 2>/dev/null || echo DETACHED)"
  done
}

# Content fingerprint (same recipe as codex-review's): staged + unstaged tracked
# diffs AND untracked file contents. Used to detect the opposite failure mode —
# codex claiming success while having changed NOTHING.
hash_cmd() { if command -v shasum >/dev/null 2>&1; then shasum; else cksum; fi; }
snapshot() {
  {
    for dir in "${repos[@]}"; do
      printf '### repo: %s\n' "$dir"
      git -C "$dir" status --porcelain 2>/dev/null
      git -C "$dir" -c core.pager=cat diff 2>/dev/null
      git -C "$dir" -c core.pager=cat diff --cached 2>/dev/null
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

cd "${repos[0]}" || { echo "CODEX_ERROR: cannot cd to ${repos[0]}"; exit 1; }

refs_before="$(ref_snapshot)"
content_before="$(snapshot)"

# --sandbox workspace-write: codex can read broadly and write ONLY inside the
# listed repos (+ /tmp). Network is disabled in this sandbox by default.
# </dev/null: the prompt is passed as an argument, so codex must not also try to
# read stdin — with a non-EOF stdin it would block or append unintended input.
codex exec --sandbox workspace-write ${add_dir_args[@]+"${add_dir_args[@]}"} -o "$out" "$prompt" </dev/null >"$log" 2>&1
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

refs_after="$(ref_snapshot)"
if [ "$refs_before" != "$refs_after" ]; then
  echo "WARNING: git HEAD or the checked-out branch changed in a repo during the run — codex may"
  echo "have committed or switched branches despite being told not to. Inspect 'git log' / 'git status'"
  echo "in each repo before continuing."
  echo
fi
content_after="$(snapshot)"
if [ "$content_before" = "$content_after" ] && [ "$refs_before" = "$refs_after" ]; then
  echo "WARNING: no file changes detected — codex's report below describes work, but the working"
  echo "tree is byte-for-byte unchanged. Treat any claimed implementation as NOT done."
  echo
fi

cat "$out"
echo
echo "----- working tree (git status --short) -----"
for dir in "${repos[@]}"; do
  echo "# ${dir}"
  git -C "$dir" status --short
done
