---
name: fable-review
description: Review a code delta, existing repository source, or supplied audit evidence with an independent Fable xhigh reviewer, autonomously fixing valid findings and re-reviewing until every finding is fixed or discarded with evidence. Use for /fable-review or an explicit request for a Fable review.
---

# Fable review

Run an autonomous review–fix–test loop using **fable at xhigh** for each
fresh, read-only review. The current session owns investigation, fixes and
testing; the reviewer only reports findings. Invoking this skill authorizes
in-scope local corrections without asking the user to approve each finding or
iteration. Continue until every in-scope finding is fixed or discarded with evidence.
If the user explicitly requests findings only, no edits, or a single pass,
honor that narrower request instead.

1. Identify the requested delta and requirements. Default to this task's
   staged/unstaged changes and new files; exclude unrelated work and pre-existing
   hunks. Use available pre-task evidence to distinguish overlapping edits.
   Ask for scope only when the available evidence cannot establish it.
   A baseline is valid only if it predates the task's first edit. Reuse it if
   available; never create or replace the task baseline during the review loop.
   Without one, use available pre-task evidence, path filters and exact hunk
   descriptions to distinguish unrelated edits; do not label the task's own
   edits as pre-existing. If overlapping ownership cannot be established,
   resolve the scope ambiguity before changing those hunks.
   Before every review, include file contents only when they are in scope and
   safe to share. Keep credentials, environment secrets and unrelated contents
   out of helper input and temporary indexes. Use explicit path filters when
   excluded files are present; if paths cannot be safely filtered, review an
   isolated sanitized copy instead. Sanitizing prompt text alone does not
   restrict the reviewer's filesystem access: do not give it a secret-bearing
   original workspace when isolation is needed.
2. Resolve this skill's physical directory when installed via symlink/junction,
   then run its [review.sh](review.sh) with a concise scope and test evidence:

   ```bash
   bash "$skill_dir/review.sh" --paths "$changed_paths" "$scope" "$target_repo"
   ```

   The wrapper pins claude, fable, and xhigh regardless of inherited
   `REVIEW_*` settings. If the user explicitly requests another effort, pass
   `--effort medium`, `--effort high`, or `--effort xhigh`; otherwise use the
   default. Never substitute another model. Requires Bash, Git, and an
   authenticated `claude` CLI. Keep the repository together: the wrapper
   depends on `../scripts/review.sh`.

   `--paths` is whitespace-separated; for filenames containing whitespace,
   omit it and give exact paths/hunks in the scope. Multiple repo roots after
   the scope permit a cross-repo review; use separate calls if filters differ.
   For committed work, use `--range <base>..<head>` (one repo), resolving the
   merge base first for a PR. Do not review history merely because the working
   tree is clean. Existing baseline snapshots can be passed with `--baseline`.
3. Triage every finding against the actual source, requirements and available
   evidence. Keep a task-local record of severity, location, impact and status:
   open, fixed (change plus validation), discarded (concrete counterevidence),
   or out of scope (why unrelated, with baseline, history or requirement evidence).
   Investigate uncertain findings yourself; do not ask the user to adjudicate
   routine technical questions. Do not discard a finding just because it is
   inconvenient, low priority, pre-existing within an explicit source audit,
   or absent from a later report. Exclude unrelated pre-existing delta hunks.
4. Fix valid in-scope findings, add meaningful regression coverage when needed,
   and run the checks appropriate to the change. Resolve test failures caused
   by the task before re-review. Keep the reviewer read-only; never give the
   wrapper write access or ask the reviewer to implement its own suggestions.
5. Run a fresh review after each batch of fixes or material new counterevidence.
   Include the original requirements, cumulative task delta, finding dispositions
   and actual test results. Preserve any valid pre-task baseline and the hunk
   exclusions established in step 1; expand path filters for files changed by fixes.
   After a committed-range review, also cover local corrections: range mode
   alone cannot see uncommitted fixes. Materialize the original range patch
   plus only the in-scope local corrections as working-tree changes over the
   original range base in an isolated temporary Git checkout. Apply the original
   binary-capable range patch with `git apply --index`, then stage the in-scope
   corrections in that temporary index, including explicitly selected ignored
   paths, subject to step 1's disclosure rule for every review. If a file
   cannot be included in full, audit sanitized task-specific hunks as evidence
   with explicit code-correctness claims and review criteria, and state what
   source context is omitted. Such an evidence report covers only those claims;
   combine it with the delta report for the rest of the task. Never call omitted,
   unreviewed changes clean. Never stage the user's checkout as part of this
   materialization.
   Staging keeps added binary/large/ignored files in the cumulative diff instead
   of the helper's capped untracked-file path. Preserve added, deleted and
   renamed files, and exclude unrelated local hunks. Run a delta
   review against that checkout so the helper supplies the full cumulative
   patch; do not merely reference committed hunks in a normal delta scope,
   whose helper prompt excludes history. No commit to the user's repository
   is needed. If commits were separately authorized by the user and all fixes
   are committed, reviewing the cumulative range is also valid. Verify the
   reviewed snapshot still matches the task's final changes before closing,
   and remove only temporary artifacts you created. For source/evidence audits,
   re-review the corrected source or evidence in the same audit mode.
   Do not rerun unchanged code and evidence hoping for a clean verdict.
6. Finish only when no actionable in-scope findings remain, required checks
   pass, and completed final review reports together cover every latest fix. A final report
   containing only disproved or evidenced out-of-scope findings can be closed
   with those dispositions explained; a literal NO_FINDINGS is not required.
   Report fixes, discards, out-of-scope findings and their reasons, validation, and the actual
   reviewer model/effort. NO_CHANGES means no matching delta, not a clean review
   of previous fixes. Errors, empty output, KILLED:, DRY_RUN: and any WARNING:
   mean incomplete review: diagnose and recover autonomously when possible.
   Do not silently substitute a model or claim completion when review failed.

Do not stop merely because one review finished or an arbitrary iteration count
was reached. If the same issue recurs without progress, investigate the cause
and change the approach. Stop with an explicit incomplete status only for a
concrete blocker that cannot be resolved within existing access and authority,
or when the user stops the work. State any unresolved findings and the exact
missing input or capability. The loop does not authorize unrelated edits,
destructive actions, publishing, deployment, or commits; request input only
when actually required to proceed within the user's scope.

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
