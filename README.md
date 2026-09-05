# useful-skills

Three engineering workflows and a standalone review skill for Claude Code or
Codex. Every engineering workflow includes planning, usage-based implementation
assignment, and independent review. A workflow runs only when you type its
slash command or ask for it by name; nothing triggers on topic alone.

| Skill | Planning | Implementation | Review |
|---|---|---|---|
| [`/low`](low/SKILL.md) | Sol or Opus **xhigh** | Sol or Opus **xhigh** | Prefer the other model, **xhigh** |
| [`/high`](high/SKILL.md) | Astra **medium** or Fable **high** | Sol or Opus **xhigh** | Prefer the model not used for planning: Astra **medium** or Fable **high** |
| [`/scientific`](scientific/SKILL.md) | Astra **high** + Fable **xhigh** | Astra **medium** or Fable **high** | The other model, at those same implementation efforts |

Scientific must be orchestrated from a Fable or Astra session and stops
otherwise; the other levels can be coordinated from any model.

Use low for routine bounded changes, high for substantial features and contract
changes, and scientific for uncertain methods requiring experiments. Scientific
planning includes a baseline, hypotheses, and measurable acceptance criteria;
its builder leaves a results record (commands, seeds, data provenance, metrics,
environment, wall time), and its reviewer reproduces the critical experiment in
a scratch worktree before judging the method, code, and evidence.

For an explicitly review-only task, `/high` uses just a fresh Astra medium or
Fable high reviewer for the supplied PR/delta or audit evidence, without
planning an implementation, building, or applying fixes. Normal `/high`
implementation tasks retain the full pipeline above.

Before implementation, the [usage fetcher](scripts/fetch-usage.py) reads each
CLI's own usage endpoint and the [selector](scripts/choose-builder.py) picks
the eligible model with the most remaining quota, accounting for shared and
model caps and a reserve for review/fixes:

```sh
python3 scripts/fetch-usage.py --reserve 10 --choose high
```

`--choose planner` ranks Astra and Fable the same way for the `/high` planner.
A CLI missing from PATH marks its models unavailable. A provider whose quota
cannot be read is omitted and reported as unknown, and the selection is a
disclosed fallback instead of an invented comparison. Hand-written
observations in the [input format](shared/usage-format.md) are the fallback
input. See the [shared workflow](shared/workflow.md).

## Standalone Sol review

[`/sol-review`](sol-review/SKILL.md) reviews only the task's delta with **Sol
xhigh**, in a fresh read-only session. It reports findings without applying
fixes or starting an implementation loop. The default scope is the task's
uncommitted changes, including staged changes and new files; unrelated work
is excluded. A commit range is reviewed with `--range <base>..<head>`.

## Install or update

Keep the entire repository together. From its root, run:

```sh
python3 scripts/install.py
```

One command installs for both CLIs: it links every skill into
`~/.claude/skills` and `~/.codex/skills`, creating either directory if missing.
On Windows use `python scripts/install.py` (or `py -3`). The installer creates
directory junctions there and symlinks on macOS/Linux. It replaces only retired
links pointing into this repository, even when their targets are already gone,
and refuses to overwrite unrelated skills; every destination is checked before
any is changed. It is safe to rerun after `git pull --ff-only`.

For a custom or single destination, pass `--skills-dir` (repeatable). Only the
listed directories are then used:

```sh
python3 scripts/install.py --skills-dir ~/.codex/skills
```

Start a new session from inside the target project. In Claude Code type `/low`,
`/high`, `/scientific`, or `/sol-review`; in Codex type `$low`, `$high`,
`$scientific`, or `$sol-review`. The engineering workflows replace
`codex-review`, `codex-implement`, `opus-codex`, and `fable-codex`; their old
invocation names are removed.

`high` and `scientific` need both the `codex` and `claude` CLIs installed and
logged in on the machine where the skill is invoked, whichever CLI starts the
workflow, because roles are dispatched through the other CLI. If either is
missing, `scientific` stops with review pending and `high` falls back to the
planning model with a disclosed note. `low` needs both for cross-model review
but may fall back to same-model review; `sol-review` needs `codex` only. The
coordinating session can run any model in either CLI, except that scientific
requires a Fable or Astra orchestrator. Every role is dispatched
as a separate process with model and effort pinned, so the session model only
affects which provider's quota pays for coordination and never substitutes for
a role, even when it matches the role's model. Missing model access is reported
rather than silently substituted. The shared helpers in `scripts/` run either
CLI (`IMPLEMENT_BACKEND` / `REVIEW_BACKEND` set to `codex` or `claude`), write
a baseline snapshot before building, and review against it with `--baseline`.
They need Bash and Git (Git Bash on Windows, not the WSL launcher); the
fetcher, selector, and installer need Python 3. The helpers preserve existing
permissions.

## Checks

These use temporary repositories and fake CLIs; they do not consume model quota:

```sh
bash tests/test.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

[MIT](LICENSE)
