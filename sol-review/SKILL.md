---
name: sol-review
description: Review only the current task's code delta with an independent Sol xhigh reviewer and report concrete findings without applying fixes. Use for /sol-review or an explicit request for a Sol review of current changes.
---

# Sol review

Run one independent, read-only review with **gpt-5.6-sol at xhigh**.
This skill produces findings only: do not implement, fix, commit, push, or
start a review/fix loop. Do not invoke the low/high/scientific workflow.

1. Identify the task's delta from the conversation and read-only Git inspection.
   By default, review its uncommitted staged/unstaged changes and new files.
   Exclude unrelated dirty files and pre-existing hunks. Use a captured session
   baseline when available; a list of dirty filenames alone cannot distinguish
   new edits in an already-dirty file. If overlapping changes cannot be scoped
   from available evidence, ask for the intended scope instead of guessing.
2. Prepare a brief scope explaining what changed, why, relevant requirements,
   the exact paths/hunks, and any baseline or existing test evidence. Resolve
   this skill's physical directory when installed via symlink/junction, then
   run its [review.sh](review.sh) helper:

   ```bash
   bash "$skill_dir/review.sh" --paths "$changed_paths" "$scope" "$target_repo"
   ```

   The wrapper pins the Codex backend, Sol, and xhigh regardless of inherited
   `REVIEW_*` settings. It uses the repository's shared review helper in a
   read-only sandbox. It requires Bash, Git, and an authenticated `codex` CLI.
   Do not silently substitute a different model or effort if Sol is unavailable.

   `--paths` is whitespace-separated; for filenames containing whitespace,
   omit it and give the exact paths and baseline/delta in the scope. Add
   `--baseline <snapshot>` when implement.sh's snapshot exists. Pass multiple
   repo roots after the scope for a cross-repo delta; use separate calls when
   each repo needs different path filters. Surrounding code may be read to
   verify a finding, but only problems introduced by the task's delta belong
   in the report.
3. Read the reviewer output and report actionable findings as ordinary Markdown,
   ordered **P0, P1, P2, P3**, with file and line, concrete impact, and suggested
   correction. Do not use code-comment directives or apply the correction.
   Discard demonstrably unsupported claims with a brief reason; do not launch
   another review merely to obtain a clean verdict.

`NO_FINDINGS` means no actionable findings in the reviewed delta. `NO_CHANGES`
means no matching uncommitted delta exists, not that committed work was reviewed.
Errors, empty output, a `KILLED:` line, or a working-tree-change warning are
not a clean review; report the limitation and inspect state read-only. Do not
run tests, formatters, or code generation during this review; read existing
test evidence instead.

If the user explicitly supplies a committed base/head, run the same wrapper
with `--range <base>..<head>`; it resolves the refs to object IDs read-only,
prints them, and gives the reviewer exactly that diff. For a patch file that
is not in Git, apply it in a detached scratch worktree and review there in the
default delta mode. Do not invent a base, review the whole repository, or fall
back to historical commits just because the working tree is clean.
