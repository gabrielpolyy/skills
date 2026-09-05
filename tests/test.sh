#!/usr/bin/env bash
# Offline tests for scripts/review.sh and scripts/implement.sh.
# A fake `codex` (tests/bin/codex) is put first on PATH, so nothing here calls
# the real CLI. Run: bash tests/test.sh
set -u

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"
review="$repo_root/scripts/review.sh"
implement="$repo_root/scripts/implement.sh"
export PATH="$here/bin:$PATH"   # tests/bin/codex is the fake
chmod +x "$here/bin/codex"

tmp="$(cd "$(mktemp -d)" && pwd -P)"   # physical path: git reports realpaths
trap 'rm -rf "$tmp"' EXIT

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "  ok   $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1"; }
# check <name> <command...>  — passes when the command exits 0.
check() { local name="$1"; shift; if "$@"; then ok "$name"; else bad "$name"; fi; }
# Small predicates usable as check commands.
contains()  { case "$1" in *"$2"*) return 0 ;; *) return 1 ;; esac; }
not()       { ! "$@"; }
eq()        { [ "$1" = "$2" ]; }
# rc_and_contains <rc> <expected rc> <text> <needle>
rc_and_contains() { [ "$1" = "$2" ] && contains "$3" "$4"; }
# toplevel <dir> — the repo root as git spells it (Git Bash: C:/..., not /tmp/...).
toplevel() { git -C "$1" rev-parse --show-toplevel; }

# A git repo with one commit and two tracked files.
mkrepo() {
  local d="$1"; mkdir -p "$d"
  git -C "$d" init -q .
  echo base > "$d/a.txt"; echo base > "$d/b.txt"
  git -C "$d" add . && git -C "$d" -c user.email=t@t -c user.name=t commit -qm init
}

# wait_pidfile <file> — wait up to ~5s for the fake codex to record its pid.
wait_pidfile() { local i; for i in $(seq 1 20); do [ -s "$1" ] && return 0; sleep 0.25; done; return 1; }
# dead_within <pid> — true when the pid is gone within ~2s.
dead_within() { local i; for i in $(seq 1 10); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.2; done; return 1; }

echo "review.sh"
# --- argument handling ---
out="$(cd "$tmp" && bash "$review" 2>&1)"; rc=$?
check "no args -> exit 2 with usage" rc_and_contains "$rc" 2 "$out" "usage:"
out="$(cd "$tmp" && bash "$review" "   " 2>&1)"; rc=$?
check "blank scope -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --paths 2>&1)"; rc=$?
check "--paths without value -> exit 2" eq "$rc" 2
mkdir -p "$tmp/notgit"
out="$(cd "$tmp/notgit" && bash "$review" "scope" 2>&1)"
check "outside git -> NOT_A_GIT_REPO" eq "$out" "NOT_A_GIT_REPO"
mkrepo "$tmp/r1"
out="$(cd "$tmp/r1" && bash "$review" "scope" "$tmp/notgit" 2>&1)"; rc=$?
check "bogus repo arg -> CODEX_ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "CODEX_ERROR: not a git repository"

# --- no-changes guard ---
out="$(cd "$tmp/r1" && bash "$review" "scope" 2>&1)"
check "clean repo -> NO_CHANGES" eq "$out" "NO_CHANGES"
echo edit >> "$tmp/r1/b.txt"
out="$(cd "$tmp/r1" && bash "$review" --paths "a.txt" "scope" 2>&1)"
check "--paths excluding the only dirty file -> NO_CHANGES" eq "$out" "NO_CHANGES"
out="$(cd "$tmp/r1" && bash "$review" --paths "b.txt" "scope" 2>&1)"
check "--paths including the dirty file -> runs codex" eq "$out" "NO_FINDINGS"
git -C "$tmp/r1" checkout -q -- b.txt
echo new > "$tmp/r1/c.txt"   # untracked only
out="$(cd "$tmp/r1" && bash "$review" --paths "c.txt" "scope" 2>&1)"
check "--paths matching only an untracked file -> runs codex" eq "$out" "NO_FINDINGS"
rm "$tmp/r1/c.txt"

# --- prompt construction (dry run) ---
echo edit >> "$tmp/r1/b.txt"
out="$(cd "$tmp/r1" && CODEX_REVIEW_DRY_RUN=1 bash "$review" --paths "b.txt src/x.ts" "my scope text" 2>&1)"
check "dry run: pathspec on diff command" contains "$out" "diff HEAD -- 'b.txt' 'src/x.ts'"
check "dry run: pathspec on status command" contains "$out" "status --short -- 'b.txt' 'src/x.ts'"
check "dry run: out-of-scope rule present" contains "$out" "ONLY these paths are in scope"
check "dry run: scope text present" contains "$out" "my scope text"
check "dry run: single repo has no cross-repo framing" not contains "$out" "MULTIPLE repositories"
out="$(cd "$tmp/r1" && CODEX_REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "dry run without --paths: bare diff HEAD" contains "$out" "diff HEAD        (staged"
check "dry run without --paths: no paths rule" not contains "$out" "ONLY these paths"
mkrepo "$tmp/r2"
out="$(cd "$tmp/r1" && CODEX_REVIEW_DRY_RUN=1 bash "$review" "scope" "$tmp/r1" "$tmp/r1" 2>&1)"
check "same repo twice dedupes (no cross-repo framing)" not contains "$out" "MULTIPLE repositories"
out="$(cd "$tmp/r1" && CODEX_REVIEW_DRY_RUN=1 bash "$review" "scope" "$tmp/r1" "$tmp/r2" 2>&1)"
check "two repos -> cross-repo framing" contains "$out" "MULTIPLE repositories"
check "two repos -> second repo listed" contains "$out" "Repo '$(toplevel "$tmp/r2")'"
mkdir -p "$tmp/fresh" && git -C "$tmp/fresh" init -q . && echo x > "$tmp/fresh/f.txt" && git -C "$tmp/fresh" add f.txt
out="$(cd "$tmp/fresh" && CODEX_REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "repo without HEAD -> no-commits instructions" contains "$out" "NO commits yet"
out="$(cd "$tmp/fresh" && bash "$review" "scope" 2>&1)"
check "repo without HEAD with staged file -> runs codex" eq "$out" "NO_FINDINGS"

# --- codex invocation and result handling ---
pf="$tmp/prompt.txt"
out="$(cd "$tmp/r1" && FAKE_CODEX_PROMPT_FILE="$pf" bash "$review" "scope via stdin" 2>&1)"
check "prompt reaches codex on stdin" contains "$(cat "$pf")" "scope via stdin"
check "output is codex's final message only" eq "$out" "NO_FINDINGS"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=fail bash "$review" "scope" 2>&1)"; rc=$?
check "codex non-zero exit -> CODEX_ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "exited 3"
check "codex non-zero exit -> log tail relayed" contains "$out" "boom"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=empty bash "$review" "scope" 2>&1)"; rc=$?
check "codex with no final message -> CODEX_ERROR" rc_and_contains "$rc" 1 "$out" "no final message"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=write FAKE_CODEX_TARGET="$tmp/r1/b.txt" bash "$review" "scope" 2>&1)"
check "tree changed during review -> WARNING" contains "$out" "WARNING: a working tree changed"
check "tree changed during review -> report still printed" contains "$out" "REPORT"

# --- signal handling: killing the script kills codex ---
pidf="$tmp/codex.pid"; rm -f "$pidf"
FAKE_CODEX_MODE=sleep FAKE_CODEX_PID_FILE="$pidf" bash "$review" "scope" "$tmp/r1" >/dev/null 2>&1 &
runner=$!
if wait_pidfile "$pidf"; then
  cpid="$(cat "$pidf")"
  kill -TERM "$runner" 2>/dev/null; wait "$runner" 2>/dev/null
  check "review: SIGTERM to script kills codex" dead_within "$cpid"
  kill -9 "$cpid" 2>/dev/null
else
  bad "review: fake codex never started"; kill -9 "$runner" 2>/dev/null
fi

echo "implement.sh"
spec="$tmp/spec.md"; printf 'Add a line to a.txt\n' > "$spec"
out="$(cd "$tmp/r1" && bash "$implement" 2>&1)"; rc=$?
check "no args -> exit 2 with usage" rc_and_contains "$rc" 2 "$out" "usage:"
: > "$tmp/empty.md"
out="$(cd "$tmp/r1" && bash "$implement" "$tmp/empty.md" 2>&1)"; rc=$?
check "empty spec -> exit 2" eq "$rc" 2
out="$(cd "$tmp/notgit" && bash "$implement" "$spec" 2>&1)"
check "outside git -> NOT_A_GIT_REPO" eq "$out" "NOT_A_GIT_REPO"
out="$(cd "$tmp/r1" && bash "$implement" "$spec" "$tmp/notgit" 2>&1)"; rc=$?
check "bogus repo arg -> CODEX_ERROR" rc_and_contains "$rc" 1 "$out" "not a git repository"
out="$(cd "$tmp/r1" && CODEX_IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" 2>&1)"
check "dry run embeds the spec" contains "$out" "Add a line to a.txt"
out="$(cd "$tmp/notgit" && CODEX_IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" "$tmp/r1" 2>&1)"
check "explicit repo arg resolves to its root" contains "$out" "cwd=$(toplevel "$tmp/r1")"
git -C "$tmp/r1" checkout -q -- . && git -C "$tmp/r1" clean -qfd
out="$(cd "$tmp/r1" && FAKE_CODEX_PROMPT_FILE="$pf" FAKE_CODEX_MODE=write FAKE_CODEX_TARGET="$tmp/r1/a.txt" bash "$implement" "$spec" 2>&1)"
check "spec reaches codex on stdin" contains "$(cat "$pf")" "Add a line to a.txt"
check "run that changed the tree -> report, no warning" eq "$out" "REPORT"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=report bash "$implement" "$spec" 2>&1)"
check "run that changed nothing -> WARNING" contains "$out" "WARNING: no working-tree change"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=fail bash "$implement" "$spec" 2>&1)"; rc=$?
check "codex non-zero exit -> CODEX_ERROR" rc_and_contains "$rc" 1 "$out" "exited 3"

rm -f "$pidf"
FAKE_CODEX_MODE=sleep FAKE_CODEX_PID_FILE="$pidf" bash "$implement" "$spec" "$tmp/r1" >/dev/null 2>&1 &
runner=$!
if wait_pidfile "$pidf"; then
  cpid="$(cat "$pidf")"
  kill -TERM "$runner" 2>/dev/null; wait "$runner" 2>/dev/null
  check "implement: SIGTERM to script kills codex" dead_within "$cpid"
  kill -9 "$cpid" 2>/dev/null
else
  bad "implement: fake codex never started"; kill -9 "$runner" 2>/dev/null
fi

echo
echo "sol-review"
sol_review="$repo_root/sol-review/review.sh"
args_file="$tmp/sol-args.txt"
out="$(CODEX_REVIEW_MODEL=gpt-6-astra CODEX_REVIEW_EFFORT=low FAKE_CODEX_ARGS_FILE="$args_file" FAKE_CODEX_PROMPT_FILE="$pf" bash "$sol_review" --paths "a.txt" "Review only the task delta" "$tmp/r1" 2>&1)"
check "Sol wrapper returns independent review report" eq "$out" "NO_FINDINGS"
check "Sol wrapper pins model despite inherited override" contains "$(cat "$args_file")" "gpt-5.6-sol"
check "Sol wrapper pins xhigh despite inherited override" contains "$(cat "$args_file")" "model_reasoning_effort=xhigh"
check "Sol wrapper enforces read-only sandbox" contains "$(cat "$args_file")" "read-only"
check "Sol wrapper passes exact delta scope" contains "$(cat "$pf")" "Review only the task delta"
out="$(bash "$sol_review" --paths "nonexistent.txt" "scope" "$tmp/r1" 2>&1)"
check "Sol wrapper does not review history when delta is empty" eq "$out" "NO_CHANGES"
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
