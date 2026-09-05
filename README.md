# useful-skills

Three independent review skills for Codex and Claude Code. Work in your chosen
session model to plan, implement, and test, then invoke a reviewer when ready.
There are no implementation workflows, planner agents, or quota selectors.

| Skill | Reviewer | Default effort |
|---|---|---|
| [`sol-review`](sol-review/SKILL.md) | `gpt-5.6-sol` via Codex | xhigh |
| [`astra-review`](astra-review/SKILL.md) | `gpt-6-astra` via Codex | high |
| [`fable-review`](fable-review/SKILL.md) | `fable` via Claude Code | xhigh |

For a second model's perspective, use Fable review after Astra work, Astra
review after Fable work, or Sol review after Opus work. Explicit effort
requests override the default: for example, work in Astra high and request
`fable-review at high`, or work in Fable xhigh and request
`astra-review at medium`. The caller's model and effort remain unchanged.

Reviews produce findings only and run in fresh read-only sessions. They do
not implement fixes, launch another workflow, or publish anything. Code review
covers the requested delta, including staged changes and new files. Use
`--audit` for whole-repository source reviews. Evidence review can check
supplied claims even with no code changes. Reviewers read
existing test results; they do not independently reproduce experiments.

## Install or update

Keep this repository together and run:

```sh
python3 scripts/install.py
```

On Windows use `python scripts/install.py` (or `py -3`). The installer links
all three skills into both `~/.claude/skills` and `~/.codex/skills`, using
symlinks on macOS/Linux and directory junctions on Windows. Rerun after
`git pull --ff-only`. It removes retired links owned by this repository
(`low`, `high`, `scientific`, `hard`, `codex-review`, `codex-implement`,
`opus-codex`, `fable-codex`) and refuses to overwrite unrelated skills.

For custom destinations, repeat `--skills-dir DIR`. Start a new session to
refresh skill discovery. Invoke `/sol-review`, `/astra-review`, or
`/fable-review` in Claude Code; use `$sol-review`, `$astra-review`, or
`$fable-review` in Codex. Each skill requires Bash, Git, and its reviewer's
CLI installed and logged in. On Windows use Git Bash for the review helpers.

## Helper usage

```sh
bash astra-review/review.sh --paths "src/app.ts tests/app.test.ts" "Scope and test results" /path/to/repo
bash fable-review/review.sh --effort high --range BASE..HEAD "Committed task scope" /path/to/repo
bash fable-review/review.sh --audit "Review current skills against their documented contracts" /path/to/repo
bash astra-review/review.sh --evidence /path/to/audit.txt "Check these conclusions" /path/to/repo
```

`--evidence` reviews supplied claims and evidence without requiring a diff.
To review code and audit conclusions together, use delta mode and include
both in the scope. `--paths` accepts whitespace-separated pathspecs; for
filenames containing spaces, omit it and specify exact files in the scope.
Legacy pre-task snapshots remain accepted via `--baseline`.

Staged and unstaged patches are kept separately, even when they cancel in the
working copy. Empty working-tree selections and committed ranges return
`NO_CHANGES`. Git collection errors stop before the reviewer is called.

Fable embeds untracked text up to 128 KiB per file and 512 KiB per repository.
Untracked symlinks include their link target without following it. Binary,
unreadable, non-regular, or oversized untracked entries receive `OMITTED`
markers and a final
`WARNING:` declaring the review incomplete. Embedded deltas over 2 MiB fail
with an error asking for a narrower scope. `REVIEW_DRY_RUN=1` previews the
prompt and recipe; `DRY_RUN:` is never a completed review.

## Checks

These run against temporary repositories and fake CLIs without model quota:

```sh
bash tests/test.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

[MIT](LICENSE)
