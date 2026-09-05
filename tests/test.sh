#!/usr/bin/env bash
# Offline tests for scripts/review.sh and scripts/implement.sh.
# Fake `codex` and `claude` CLIs (tests/bin) are put first on PATH, so nothing
# here calls a real CLI. Run: bash tests/test.sh
set -u

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/.." && pwd)"
review="$repo_root/scripts/review.sh"
implement="$repo_root/scripts/implement.sh"
export PATH="$here/bin:$PATH"   # tests/bin/codex and tests/bin/claude are the fakes
chmod +x "$here/bin/codex" "$here/bin/claude"

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
first_line() { printf '%s\n' "$1" | head -n 1; }
last_line()  { printf '%s\n' "$1" | tail -n 1; }
gitc() { git -C "$1" -c user.email=t@t -c user.name=t "${@:2}"; }

# A git repo with one commit and two tracked files.
mkrepo() {
  local d="$1"; mkdir -p "$d"
  git -C "$d" init -q .
  echo base > "$d/a.txt"; echo base > "$d/b.txt"
  git -C "$d" add . && gitc "$d" commit -qm init
}

# wait_pidfile <file> — wait up to ~5s for a fake CLI to record its pid.
wait_pidfile() { local i; for i in $(seq 1 20); do [ -s "$1" ] && return 0; sleep 0.25; done; return 1; }
# dead_within <pid> — true when the pid is gone within ~2s.
dead_within() { local i; for i in $(seq 1 10); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.2; done; return 1; }
# kill_test <label> <pidfile> <outfile> <command...> — run the helper in the
# background, SIGTERM it once the fake is up, and check the child died, the
# KILLED: line was printed, and the exit code is 143.
kill_test() {
  local label="$1" pidf="$2" outf="$3"; shift 3
  rm -f "$pidf"
  "$@" >"$outf" 2>&1 &
  local runner=$!
  if wait_pidfile "$pidf"; then
    local cpid; cpid="$(cat "$pidf")"
    kill -TERM "$runner" 2>/dev/null; wait "$runner" 2>/dev/null; local rc=$?
    check "$label: SIGTERM to script kills the child" dead_within "$cpid"
    check "$label: KILLED line printed, exit 143" rc_and_contains "$rc" 143 "$(cat "$outf")" "KILLED:"
    kill -9 "$cpid" 2>/dev/null
  else
    bad "$label: fake CLI never started"; kill -9 "$runner" 2>/dev/null
  fi
}

echo "review.sh"
# --- argument handling ---
out="$(cd "$tmp" && bash "$review" 2>&1)"; rc=$?
check "no args -> exit 2 with usage" rc_and_contains "$rc" 2 "$out" "usage:"
out="$(cd "$tmp" && bash "$review" "   " 2>&1)"; rc=$?
check "blank scope -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --paths 2>&1)"; rc=$?
check "--paths without value -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --paths "" "scope" 2>&1)"; rc=$?
check "--paths with empty value -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --paths "   " "scope" 2>&1)"; rc=$?
check "--paths with blank value -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --range "abc" "scope" 2>&1)"; rc=$?
check "--range without .. -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && bash "$review" --baseline "$tmp/missing" "scope" 2>&1)"; rc=$?
check "--baseline with missing file -> exit 2" eq "$rc" 2
out="$(cd "$tmp" && REVIEW_BACKEND=bogus bash "$review" "scope" 2>&1)"; rc=$?
check "unknown backend -> exit 2" rc_and_contains "$rc" 2 "$out" "REVIEW_BACKEND"
mkdir -p "$tmp/notgit"
out="$(cd "$tmp/notgit" && bash "$review" "scope" 2>&1)"
check "outside git -> NOT_A_GIT_REPO" eq "$out" "NOT_A_GIT_REPO"
mkrepo "$tmp/r1"
out="$(cd "$tmp/r1" && bash "$review" "scope" "$tmp/notgit" 2>&1)"; rc=$?
check "bogus repo arg -> ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "ERROR: not a git repository"
printf 'x\n' > "$tmp/snap0"
out="$(cd "$tmp/r1" && bash "$review" --baseline "$tmp/snap0" --range "HEAD..HEAD" "scope" 2>&1)"; rc=$?
check "--baseline and --range together -> exit 2" eq "$rc" 2

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
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" --paths "b.txt src/x.ts" "my scope text" 2>&1)"
check "dry run: full codex recipe" contains "$out" "codex exec --sandbox read-only -m gpt-6-astra -c model_reasoning_effort=medium -o <tmp> -"
check "dry run: pathspec on diff command" contains "$out" "diff HEAD -- 'b.txt' 'src/x.ts'"
check "dry run: pathspec on status command" contains "$out" "status --short -- 'b.txt' 'src/x.ts'"
check "dry run: out-of-scope rule present" contains "$out" "ONLY these paths are in scope"
check "dry run: scope text present" contains "$out" "my scope text"
check "dry run: single repo has no cross-repo framing" not contains "$out" "MULTIPLE repositories"
check "dry run: no baseline section without --baseline" not contains "$out" "BASELINE:"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "dry run without --paths: bare diff HEAD" contains "$out" "diff HEAD        (staged"
check "dry run without --paths: no paths rule" not contains "$out" "ONLY these paths"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 REVIEW_MODEL=gpt-5.6-sol REVIEW_EFFORT=xhigh bash "$review" "scope" 2>&1)"
check "dry run: model/effort overrides appear in the recipe" contains "$out" "-m gpt-5.6-sol -c model_reasoning_effort=xhigh"
mkrepo "$tmp/r2"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" "scope" "$tmp/r1" "$tmp/r1" 2>&1)"
check "same repo twice dedupes (no cross-repo framing)" not contains "$out" "MULTIPLE repositories"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" "scope" "$tmp/r1" "$tmp/r2" 2>&1)"
check "two repos -> cross-repo framing" contains "$out" "MULTIPLE repositories"
check "two repos -> second repo listed" contains "$out" "Repo '$(toplevel "$tmp/r2")'"
mkdir -p "$tmp/fresh" && git -C "$tmp/fresh" init -q . && echo x > "$tmp/fresh/f.txt" && git -C "$tmp/fresh" add f.txt
out="$(cd "$tmp/fresh" && REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "repo without HEAD -> no-commits instructions" contains "$out" "NO commits yet"
out="$(cd "$tmp/fresh" && bash "$review" "scope" 2>&1)"
check "repo without HEAD with staged file -> runs codex" eq "$out" "NO_FINDINGS"
# quoting: an apostrophe in a path and a space in the repo root
echo q > "$tmp/r1/it's.txt"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" --paths "it's.txt" "scope" 2>&1)"
check "apostrophe in --paths is shell-quoted" contains "$out" "diff HEAD -- 'it'\\''s.txt'"
rm "$tmp/r1/it's.txt"
mkrepo "$tmp/my repo"; echo edit >> "$tmp/my repo/a.txt"
out="$(cd "$tmp/my repo" && REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "space in repo root is shell-quoted" contains "$out" "git -C '$(toplevel "$tmp/my repo")' diff HEAD"
# claude backend embeds the delta instead of gather instructions
echo new > "$tmp/r1/c.txt"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" "scope" 2>&1)"
check "claude dry run: full claude recipe" contains "$out" "claude -p --model fable --effort high --tools Read,Glob,Grep --strict-mcp-config --no-session-persistence"
check "claude dry run: embeds the patch" contains "$out" "+edit"
check "claude dry run: embeds untracked file contents" contains "$out" "### untracked file: c.txt"
check "claude dry run: no gather-it-yourself block" not contains "$out" "Gather the changes yourself"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" --paths "c.txt" "scope" 2>&1)"
check "claude dry run: --paths restricts the embedded delta" not contains "$out" "+edit"
check "claude dry run: --paths keeps the in-scope untracked file" contains "$out" "### untracked file: c.txt"
rm "$tmp/r1/c.txt"

# --- codex invocation and result handling ---
pf="$tmp/prompt.txt"; af="$tmp/args.txt"
out="$(cd "$tmp/r1" && FAKE_CODEX_PROMPT_FILE="$pf" FAKE_CODEX_ARGS_FILE="$af" bash "$review" "scope via stdin" 2>&1)"
check "prompt reaches codex on stdin" contains "$(cat "$pf")" "scope via stdin"
check "output is codex's final message only" eq "$out" "NO_FINDINGS"
out="$(cd "$tmp/r1" && bash "$review" "scope" 2>"$tmp/err.txt")"
check "normal run prints nothing on stderr (no job-control noise)" eq "$(cat "$tmp/err.txt")" ""
check "codex argv: read-only sandbox" contains "$(cat "$af")" "sandbox=read-only"
check "codex argv: default model" contains "$(cat "$af")" "gpt-6-astra"
check "codex argv: default effort" contains "$(cat "$af")" "model_reasoning_effort=medium"
check "codex argv: prompt from stdin (trailing -)" eq "$(last_line "$(cat "$af")")" "-"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=fail bash "$review" "scope" 2>&1)"; rc=$?
check "codex non-zero exit -> ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "exited 3"
check "codex non-zero exit -> log tail relayed" contains "$out" "boom"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=empty bash "$review" "scope" 2>&1)"; rc=$?
check "codex with no final message -> ERROR" rc_and_contains "$rc" 1 "$out" "no final message"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=write FAKE_CODEX_TARGET="$tmp/r1/b.txt" bash "$review" "scope" 2>&1)"
check "tree changed during review -> WARNING" contains "$out" "WARNING: a working tree changed"
check "tree changed during review -> report still printed" contains "$out" "REPORT"
# fingerprint covers the full content of large untracked files
head -c 2097152 /dev/zero | tr '\0' a > "$tmp/r1/big.bin"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=run FAKE_CODEX_CMD="head -c 2097152 /dev/zero | tr '\\0' b > big.bin" bash "$review" "scope" 2>&1)"
check "same-size rewrite of a large untracked file -> WARNING" contains "$out" "WARNING: a working tree changed"
rm "$tmp/r1/big.bin"

# --- claude invocation and result handling ---
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude FAKE_CLAUDE_PROMPT_FILE="$pf" FAKE_CLAUDE_ARGS_FILE="$af" bash "$review" "scope via stdin" 2>&1)"
check "claude: prompt reaches claude on stdin" contains "$(cat "$pf")" "scope via stdin"
check "claude: output is the final message only" eq "$out" "NO_FINDINGS"
args="$(cat "$af")"
check "claude argv: print mode" contains "$args" "-p"
check "claude argv: model" contains "$args" "--model
fable"
check "claude argv: effort" contains "$args" "--effort
high"
check "claude argv: read-only tools" contains "$args" "--tools
Read,Glob,Grep"
check "claude argv: strict mcp + no persistence" contains "$args" "--strict-mcp-config
--no-session-persistence"
check "claude argv: no permission mode for a reviewer" not contains "$args" "--permission-mode"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_MODEL=opus REVIEW_EFFORT=xhigh FAKE_CLAUDE_ARGS_FILE="$af" bash "$review" "scope" 2>&1)"
check "claude argv: model/effort overrides" contains "$(cat "$af")" "opus
--effort
xhigh"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude FAKE_CLAUDE_MODE=fail bash "$review" "scope" 2>&1)"; rc=$?
check "claude non-zero exit -> ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "claude exited 3"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude FAKE_CLAUDE_MODE=empty bash "$review" "scope" 2>&1)"; rc=$?
check "claude with no final message -> ERROR" rc_and_contains "$rc" 1 "$out" "no final message"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude FAKE_CLAUDE_MODE=run FAKE_CLAUDE_CMD="echo x >> b.txt" bash "$review" "scope" 2>&1)"
check "claude: tree changed during review -> WARNING" contains "$out" "WARNING: a working tree changed"

# --- signal handling: killing the script kills the child ---
kill_test "review/codex" "$tmp/child.pid" "$tmp/killed.out" env FAKE_CODEX_MODE=sleep FAKE_CODEX_PID_FILE="$tmp/child.pid" bash "$review" "scope" "$tmp/r1"
kill_test "review/claude" "$tmp/child.pid" "$tmp/killed.out" env REVIEW_BACKEND=claude FAKE_CLAUDE_MODE=sleep FAKE_CLAUDE_PID_FILE="$tmp/child.pid" bash "$review" "scope" "$tmp/r1"

# --- committed ranges ---
git -C "$tmp/r1" checkout -q -- . && git -C "$tmp/r1" clean -qfd
echo more >> "$tmp/r1/a.txt"; gitc "$tmp/r1" commit -qam second
base="$(git -C "$tmp/r1" rev-parse HEAD~1)"; head="$(git -C "$tmp/r1" rev-parse HEAD)"
out="$(cd "$tmp/r1" && bash "$review" --range "HEAD~1..HEAD" "scope" 2>&1)"
check "--range: RANGE line with resolved object IDs" eq "$(first_line "$out")" "RANGE: $base $head"
check "--range: clean tree still runs the review" eq "$(last_line "$out")" "NO_FINDINGS"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" --range "HEAD~1..HEAD" --paths "a.txt" "scope" 2>&1)"
check "--range: codex prompt names the exact diff" contains "$out" "diff $base $head -- 'a.txt'"
check "--range: no working-tree gather instructions" not contains "$out" "diff HEAD"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" --range "HEAD~1..HEAD" "scope" 2>&1)"
check "--range: claude prompt embeds the range diff" contains "$out" "+more"
# claude sees the working tree, so the prompt must carry each touched file AS AT THE HEAD.
echo wip >> "$tmp/r1/a.txt"   # working tree now differs from the reviewed head
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude FAKE_CLAUDE_PROMPT_FILE="$pf" bash "$review" --range "HEAD~1..HEAD" "scope" 2>&1)"
check "--range: claude review runs with a dirty tree" eq "$(last_line "$out")" "NO_FINDINGS"
check "--range: claude prompt embeds the touched file at the head" contains "$(cat "$pf")" "### file at $head: a.txt
base
more"
check "--range: embedded file is the head version, not the working tree" not contains "$(cat "$pf")" "wip"
check "--range: prompt warns the working tree may differ from the head" contains "$(cat "$pf")" "The working tree may differ from the reviewed head"
check "--range: prompt makes the embedded contents authoritative" contains "$(cat "$pf")" "embedded file contents are authoritative"
git -C "$tmp/r1" checkout -q -- a.txt
# deleted and binary files are not embedded; --paths restricts the embedded files
printf '\000\001\002' > "$tmp/r1/bin.dat"; echo text > "$tmp/r1/c.txt"
git -C "$tmp/r1" rm -q b.txt && git -C "$tmp/r1" add bin.dat c.txt && gitc "$tmp/r1" commit -qm third
head3="$(git -C "$tmp/r1" rev-parse HEAD)"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" --range "HEAD~1..HEAD" "scope" 2>&1)"
check "--range: added text file is embedded at the head" contains "$out" "### file at $head3: c.txt
text"
check "--range: deleted file is not embedded" not contains "$out" "### file at $head3: b.txt"
check "--range: binary file is not embedded" not contains "$out" "### file at $head3: bin.dat"
out="$(cd "$tmp/r1" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" --range "HEAD~1..HEAD" --paths "bin.dat" "scope" 2>&1)"
check "--range: --paths restricts the embedded files" not contains "$out" "### file at $head3: c.txt"
out="$(cd "$tmp/r1" && REVIEW_DRY_RUN=1 bash "$review" --range "HEAD~1..HEAD" "scope" 2>&1)"
check "--range: codex prompt does not embed file contents" not contains "$out" "### file at"
out="$(cd "$tmp/r1" && bash "$review" --range "HEAD~1..nope" "scope" 2>&1)"; rc=$?
check "--range: unresolvable ref -> ERROR" rc_and_contains "$rc" 1 "$out" "cannot resolve range"
out="$(cd "$tmp/r1" && bash "$review" --range "HEAD~1..HEAD" "scope" "$tmp/r1" "$tmp/r2" 2>&1)"; rc=$?
check "--range: two repos -> exit 2" eq "$rc" 2

echo "implement.sh"
spec="$tmp/spec.md"; printf 'Add a line to a.txt\n' > "$spec"
out="$(cd "$tmp/r1" && bash "$implement" 2>&1)"; rc=$?
check "no args -> exit 2 with usage" rc_and_contains "$rc" 2 "$out" "usage:"
: > "$tmp/empty.md"
out="$(cd "$tmp/r1" && bash "$implement" "$tmp/empty.md" 2>&1)"; rc=$?
check "empty spec -> exit 2" eq "$rc" 2
out="$(cd "$tmp/r1" && IMPLEMENT_BACKEND=bogus bash "$implement" "$spec" 2>&1)"; rc=$?
check "unknown backend -> exit 2" eq "$rc" 2
out="$(cd "$tmp/notgit" && bash "$implement" "$spec" 2>&1)"
check "outside git -> NOT_A_GIT_REPO" eq "$out" "NOT_A_GIT_REPO"
out="$(cd "$tmp/r1" && bash "$implement" "$spec" "$tmp/notgit" 2>&1)"; rc=$?
check "bogus repo arg -> ERROR" rc_and_contains "$rc" 1 "$out" "not a git repository"
out="$(cd "$tmp/r1" && IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" 2>&1)"
check "dry run embeds the spec" contains "$out" "Add a line to a.txt"
check "dry run: full codex recipe" contains "$out" "codex exec --sandbox workspace-write -m gpt-6-astra -c model_reasoning_effort=medium -o <tmp> -"
check "dry run: dependency rule follows the spec" contains "$out" "Add a dependency only when the spec names it"
check "dry run: no blanket dependency ban" not contains "$out" "no new dependencies"
out="$(cd "$tmp/r1" && IMPLEMENT_BACKEND=claude IMPLEMENT_MODEL=opus IMPLEMENT_EFFORT=xhigh IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" 2>&1)"
check "dry run: full claude recipe" contains "$out" "claude -p --model opus --effort xhigh --permission-mode acceptEdits --no-session-persistence"
out="$(cd "$tmp/notgit" && IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" "$tmp/r1" 2>&1)"
check "explicit repo arg resolves to its root" contains "$out" "cwd=$(toplevel "$tmp/r1")"
out="$(cd "$tmp/my repo" && IMPLEMENT_DRY_RUN=1 bash "$implement" "$spec" 2>&1)"
check "space in repo root is shell-quoted in the prompt" contains "$out" "repository at '$(toplevel "$tmp/my repo")'"
git -C "$tmp/r1" checkout -q -- . && git -C "$tmp/r1" clean -qfd
out="$(cd "$tmp/r1" && FAKE_CODEX_PROMPT_FILE="$pf" FAKE_CODEX_ARGS_FILE="$af" FAKE_CODEX_MODE=write FAKE_CODEX_TARGET="$tmp/r1/a.txt" bash "$implement" "$spec" 2>&1)"; rc=$?
check "spec reaches codex on stdin" contains "$(cat "$pf")" "Add a line to a.txt"
check "run that changed the tree -> SNAPSHOT line first" contains "$(first_line "$out")" "SNAPSHOT: "
check "run that changed the tree -> report, no warning, exit 0" rc_and_contains "$rc" 0 "$(last_line "$out")" "REPORT"
check "run that changed the tree -> no warning" not contains "$out" "WARNING"
check "codex argv: workspace-write sandbox" contains "$(cat "$af")" "sandbox=workspace-write"
check "codex argv: default model and effort" contains "$(cat "$af")" "gpt-6-astra
-c
model_reasoning_effort=medium"
check "codex argv: prompt from stdin (trailing -)" eq "$(last_line "$(cat "$af")")" "-"
snapf="${out#SNAPSHOT: }"; snapf="$(first_line "$snapf")"
check "snapshot file records HEAD" contains "$(cat "$snapf")" "### head: $(git -C "$tmp/r1" rev-parse HEAD)"
check "snapshot file records the pre-run status (clean)" contains "$(cat "$snapf")" "### status
### unstaged"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=report bash "$implement" "$spec" 2>&1)"; rc=$?
check "run that changed nothing -> WARNING, exit 3" rc_and_contains "$rc" 3 "$out" "WARNING: no working-tree change"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=run FAKE_CODEX_CMD="echo c >> a.txt && git add a.txt && git -c user.email=t@t -c user.name=t commit -qm oops" bash "$implement" "$spec" 2>&1)"; rc=$?
check "run that committed -> WARNING HEAD moved, exit 3" rc_and_contains "$rc" 3 "$out" "WARNING: HEAD moved"
out="$(cd "$tmp/r1" && FAKE_CODEX_MODE=fail bash "$implement" "$spec" 2>&1)"; rc=$?
check "codex non-zero exit -> ERROR" rc_and_contains "$rc" 1 "$out" "exited 3"
# claude backend
out="$(cd "$tmp/r1" && IMPLEMENT_BACKEND=claude FAKE_CLAUDE_PROMPT_FILE="$pf" FAKE_CLAUDE_ARGS_FILE="$af" FAKE_CLAUDE_MODE=run FAKE_CLAUDE_CMD="echo changed >> b.txt" FAKE_CLAUDE_OUTPUT=REPORT bash "$implement" "$spec" 2>&1)"; rc=$?
check "claude: spec reaches claude on stdin" contains "$(cat "$pf")" "Add a line to a.txt"
check "claude: report is the final message, exit 0" rc_and_contains "$rc" 0 "$(last_line "$out")" "REPORT"
args="$(cat "$af")"
check "claude argv: model and effort defaults" contains "$args" "--model
fable
--effort
high"
check "claude argv: acceptEdits permission mode" contains "$args" "--permission-mode
acceptEdits"
check "claude argv: no persistence" contains "$args" "--no-session-persistence"
check "claude argv: never bypasses permissions" not contains "$args" "bypassPermissions"
out="$(cd "$tmp/r1" && IMPLEMENT_BACKEND=claude FAKE_CLAUDE_MODE=fail bash "$implement" "$spec" 2>&1)"; rc=$?
check "claude non-zero exit -> ERROR" rc_and_contains "$rc" 1 "$out" "claude exited 3"

kill_test "implement/codex" "$tmp/child.pid" "$tmp/killed.out" env FAKE_CODEX_MODE=sleep FAKE_CODEX_PID_FILE="$tmp/child.pid" bash "$implement" "$spec" "$tmp/r1"
kill_test "implement/claude" "$tmp/child.pid" "$tmp/killed.out" env IMPLEMENT_BACKEND=claude FAKE_CLAUDE_MODE=sleep FAKE_CLAUDE_PID_FILE="$tmp/child.pid" bash "$implement" "$spec" "$tmp/r1"

echo "baseline round trip"
# A: the task restores a pre-existing dirty file to its committed contents.
mkrepo "$tmp/r3"; echo dirty >> "$tmp/r3/b.txt"
out="$(cd "$tmp/r3" && IMPLEMENT_SNAPSHOT="$tmp/snapA" FAKE_CODEX_MODE=run FAKE_CODEX_CMD="git checkout -- b.txt" bash "$implement" "$spec" 2>&1)"; rc=$?
check "IMPLEMENT_SNAPSHOT chooses the snapshot path" eq "$(first_line "$out")" "SNAPSHOT: $tmp/snapA"
check "snapshot records the pre-existing edit" contains "$(cat "$tmp/snapA")" "+dirty"
check "restoring a dirty file counts as a change (exit 0)" eq "$rc" 0
out="$(cd "$tmp/r3" && bash "$review" "scope" 2>&1)"
check "restored file without --baseline -> NO_CHANGES" eq "$out" "NO_CHANGES"
out="$(cd "$tmp/r3" && REVIEW_DRY_RUN=1 bash "$review" --baseline "$tmp/snapA" "scope" 2>&1)"
check "--baseline: prompt embeds the baseline patch" contains "$out" "+dirty"
check "--baseline: prompt explains the delta is baseline vs current" contains "$out" "DIFFERENCE
between that baseline and the current state"
out="$(cd "$tmp/r3" && bash "$review" --baseline "$tmp/snapA" "scope" 2>&1)"
check "restored file with --baseline -> review runs" eq "$out" "NO_FINDINGS"
# B: a staged change is cancelled in the working tree.
mkrepo "$tmp/r4"; echo staged >> "$tmp/r4/a.txt"; git -C "$tmp/r4" add a.txt
out="$(cd "$tmp/r4" && IMPLEMENT_SNAPSHOT="$tmp/snapB" FAKE_CODEX_MODE=run FAKE_CODEX_CMD="git show HEAD:a.txt > a.txt" bash "$implement" "$spec" 2>&1)"; rc=$?
check "cancelling a staged change counts as a change (exit 0)" eq "$rc" 0
out="$(cd "$tmp/r4" && bash "$review" "scope" 2>&1)"
check "cancelled staged change without --baseline -> NO_CHANGES" eq "$out" "NO_CHANGES"
out="$(cd "$tmp/r4" && bash "$review" --baseline "$tmp/snapB" "scope" 2>&1)"
check "cancelled staged change with --baseline -> review runs" eq "$out" "NO_FINDINGS"
# C: the normal case, and an untouched tree.
mkrepo "$tmp/r5"
out="$(cd "$tmp/r5" && IMPLEMENT_SNAPSHOT="$tmp/snapC" FAKE_CODEX_MODE=report bash "$implement" "$spec" 2>&1)"
out="$(cd "$tmp/r5" && bash "$review" --baseline "$tmp/snapC" "scope" 2>&1)"
check "untouched tree with --baseline -> NO_CHANGES" eq "$out" "NO_CHANGES"
echo work >> "$tmp/r5/a.txt"
out="$(cd "$tmp/r5" && bash "$review" --baseline "$tmp/snapC" --paths "a.txt" "scope" 2>&1)"
check "normal edit with --baseline and --paths -> review runs" eq "$out" "NO_FINDINGS"
# D: the snapshot lives INSIDE the repo (untracked, not ignored) and is given as a relative path.
mkrepo "$tmp/r6"
out="$(cd "$tmp/r6" && IMPLEMENT_SNAPSHOT="snap.txt" FAKE_CODEX_MODE=report bash "$implement" "$spec" 2>&1)"; rc=$?
check "in-repo snapshot: SNAPSHOT line names the resolved path" eq "$(first_line "$out")" "SNAPSHOT: $tmp/r6/snap.txt"
check "in-repo snapshot: unchanged run is still detected (exit 3)" rc_and_contains "$rc" 3 "$out" "WARNING: no working-tree change"
check "in-repo snapshot: snapshot records HEAD" contains "$(cat "$tmp/r6/snap.txt")" "### head: $(git -C "$tmp/r6" rev-parse HEAD)"
check "in-repo snapshot: snapshot does not list itself" not contains "$(cat "$tmp/r6/snap.txt")" "snap.txt"
out="$(cd "$tmp/r6" && bash "$review" --baseline "snap.txt" "scope" 2>&1)"
check "in-repo snapshot: --baseline on it with no edits -> NO_CHANGES" eq "$out" "NO_CHANGES"
echo work >> "$tmp/r6/a.txt"
out="$(cd "$tmp/r6" && REVIEW_BACKEND=claude REVIEW_DRY_RUN=1 bash "$review" --baseline "$tmp/r6/snap.txt" "scope" 2>&1)"
check "in-repo snapshot: not embedded as an untracked file" not contains "$out" "### untracked file: snap.txt"
check "in-repo snapshot: prompt tells the reviewer to ignore it" contains "$out" "The snapshot file itself (snap.txt, inside the repo) is not part of the delta"
out="$(cd "$tmp/r6" && bash "$review" --baseline "$tmp/r6/snap.txt" "scope" 2>&1)"
check "in-repo snapshot: a real edit with --baseline -> review runs" eq "$out" "NO_FINDINGS"
out="$(cd "$tmp/r6" && IMPLEMENT_SNAPSHOT="$tmp/r6/snap.txt" FAKE_CODEX_MODE=write FAKE_CODEX_TARGET="$tmp/r6/b.txt" bash "$implement" "$spec" 2>&1)"; rc=$?
check "in-repo snapshot: rerun over the old snapshot succeeds (exit 0)" rc_and_contains "$rc" 0 "$(last_line "$out")" "REPORT"
check "in-repo snapshot: rerun snapshot does not list itself" not contains "$(cat "$tmp/r6/snap.txt")" "snap.txt"
check "in-repo snapshot: rerun snapshot records the earlier edit" contains "$(cat "$tmp/r6/snap.txt")" "+work"
out="$(cd "$tmp/r6" && IMPLEMENT_SNAPSHOT="$tmp/nodir/snap.txt" FAKE_CODEX_MODE=report bash "$implement" "$spec" 2>&1)"; rc=$?
check "snapshot in a missing directory -> ERROR, exit 1" rc_and_contains "$rc" 1 "$out" "ERROR: snapshot directory does not exist"

echo
echo "sol-review"
sol_review="$repo_root/sol-review/review.sh"
args_file="$tmp/sol-args.txt"
echo edit >> "$tmp/r1/a.txt"
out="$(REVIEW_BACKEND=claude REVIEW_MODEL=gpt-6-astra REVIEW_EFFORT=low FAKE_CODEX_ARGS_FILE="$args_file" FAKE_CODEX_PROMPT_FILE="$pf" bash "$sol_review" --paths "a.txt" "Review only the task delta" "$tmp/r1" 2>&1)"
check "Sol wrapper returns independent review report" eq "$out" "NO_FINDINGS"
check "Sol wrapper pins the codex backend despite inherited override" contains "$(cat "$args_file")" "sandbox=read-only"
check "Sol wrapper pins model despite inherited override" contains "$(cat "$args_file")" "gpt-5.6-sol"
check "Sol wrapper pins xhigh despite inherited override" contains "$(cat "$args_file")" "model_reasoning_effort=xhigh"
check "Sol wrapper passes exact delta scope" contains "$(cat "$pf")" "Review only the task delta"
out="$(bash "$sol_review" --paths "nonexistent.txt" "scope" "$tmp/r1" 2>&1)"
check "Sol wrapper does not review history when delta is empty" eq "$out" "NO_CHANGES"
out="$(bash "$sol_review" --range "HEAD~1..HEAD" "scope" "$tmp/r1" 2>&1)"
check "Sol wrapper passes --range through" contains "$(first_line "$out")" "RANGE: "
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
