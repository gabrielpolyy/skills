---
name: sol-review
description: Review a code delta, existing repository source, or supplied audit evidence with an independent Sol xhigh reviewer, reporting findings without fixes. Use for /sol-review or an explicit request for a Sol review.
---

# Sol review

Run one fresh, read-only review with **gpt-5.6-sol at xhigh**. The current
session owns planning, implementation, and testing; this skill delegates only
review. Return findings without applying fixes or starting a fix/review loop.
An already-authorized caller may act on the report under its own policy.

1. Identify the requested delta and requirements. Default to this task's
   staged/unstaged changes and new files; exclude unrelated work and pre-existing
   hunks. Use available pre-task evidence to distinguish overlapping edits.
   Ask for scope only when the available evidence cannot establish it.
2. Resolve this skill's physical directory when installed via symlink/junction,
   then run its [review.sh](review.sh) with a concise scope and test evidence:

   ```bash
   bash "$skill_dir/review.sh" --paths "$changed_paths" "$scope" "$target_repo"
   ```

   The wrapper pins codex, gpt-5.6-sol, and xhigh regardless of inherited
   `REVIEW_*` settings. If the user explicitly requests another effort, pass
   `--effort medium`, `--effort high`, or `--effort xhigh`; otherwise use the
   default. Never substitute another model. Requires Bash, Git, and an
   authenticated `codex` CLI. Keep the repository together: the wrapper
   depends on `../scripts/review.sh`.

   `--paths` is whitespace-separated; for filenames containing whitespace,
   omit it and give exact paths/hunks in the scope. Multiple repo roots after
   the scope permit a cross-repo review; use separate calls if filters differ.
   For committed work, use `--range <base>..<head>` (one repo), resolving the
   merge base first for a PR. Do not review history merely because the working
   tree is clean. Existing baseline snapshots can be passed with `--baseline`.
3. Report concrete findings ordered P0–P3, with file/line or evidence reference,
   impact, and suggested correction. Discard demonstrably unsupported claims
   with a brief reason. Report the actual model and effort. `NO_FINDINGS` means
   no actionable findings within scope; `NO_CHANGES` means no matching delta.
   Errors, empty output, `KILLED:`, `DRY_RUN:`, or any `WARNING:` mean incomplete
   review. Do not rerun an unchanged review to obtain a clean verdict.

## Whole-repository source review

For an explicit review of existing code (including a clean tree), use
`--audit "$scope_and_criteria" "$target_repo"`. Optional `--paths` restricts
the source files; do not combine audit mode with evidence, baseline, or range.
The reviewer reads current tracked and untracked source and reports existing
defects. Use delta mode for ordinary task reviews.

## Audit evidence without a code delta

When asked to review an audit, experiment, or conclusions, write the supplied
claims, relevant source evidence, criteria, and limitations to a task-local
text file and pass `--evidence "$evidence_file" "$scope" "$target_repo"`.
This mode works in a clean Git repository and reviews only that evidence;
it cannot be combined with `--paths`, `--range`, or `--baseline`. For a review
covering both a code delta and audit conclusions, use normal delta mode and
include the evidence in the scope or point to exact evidence files there.

The reviewer challenges assumptions, calculations, and whether the evidence
supports the claims. It reads existing test/experiment results; it does not
run tests, reproduce experiments, modify files, or claim independent
reproduction. The caller must arrange any necessary execution separately.
