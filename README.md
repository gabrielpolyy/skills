# useful-skills

Three engineering workflows and a standalone review skill for Claude Code or
Codex. Every engineering workflow includes planning, usage-based implementation
assignment, and independent review.

| Skill | Planning | Implementation | Review |
|---|---|---|---|
| [`/low`](low/SKILL.md) | Sol or Opus **xhigh** | Sol or Opus **xhigh** | Prefer the other model, **xhigh** |
| [`/high`](high/SKILL.md) | Astra **medium** + Fable **high** | Sol or Opus **xhigh** | Astra **medium** or Fable **high** |
| [`/scientific`](scientific/SKILL.md) | Astra **high** + Fable **xhigh** | Astra **medium** or Fable **high** | The other model, at those same implementation efforts |

Use low for routine bounded changes, high for substantial features and contract
changes, and scientific for uncertain methods requiring experiments. Scientific
planning includes a baseline, hypotheses, and measurable acceptance criteria;
its review examines the method and reproducible evidence as well as code.

Before implementation, select the eligible model with the most remaining
quota, accounting for all shared/model caps and a reserve for review/fixes.
Keep the selected builder through fixes unless it cannot finish. Quota cannot
always be read automatically: unavailable or stale usage is explicitly reported
as unknown, with a disclosed fallback instead of an invented usage comparison.
The [selector](scripts/choose-builder.py) consumes fresh normalized observations
from the agent's available usage surface; it does not query provider accounts.
See the [input format](shared/usage-format.md) and [shared workflow](shared/workflow.md).

## Standalone Sol review

[`/sol-review`](sol-review/SKILL.md) reviews only the task's delta with **Sol
xhigh**, in a fresh read-only session. It reports findings without applying
fixes or starting an implementation loop. The default scope is the task's
uncommitted changes, including staged changes and new files; unrelated work
is excluded. An explicitly requested commit range or patch can also be reviewed.

## Install or update

Keep the entire repository together. From its root, run:

```sh
python3 scripts/install.py
```

On Windows use `python scripts/install.py` (or `py -3`). The installer creates
directory junctions there and symlinks on macOS/Linux. It replaces only retired
links pointing into this repository and refuses to overwrite unrelated skills.
It is safe to rerun after `git pull --ff-only`.

The default destination is `~/.claude/skills`. To also install for Codex:

```sh
python3 scripts/install.py --skills-dir ~/.codex/skills
```

Start a new session to discover `/low`, `/high`, `/scientific`, and `/sol-review`
(in Codex, use `$low`, `$high`, `$scientific`, or `$sol-review`). The engineering
workflows replace `codex-review`,
`codex-implement`, `opus-codex`, and `fable-codex`; their old invocation names
are removed. Their Codex execution helpers remain internal scripts.

Roles require actual access to their named models through native agent tools
or the `codex`/`claude` CLIs. The coordinator can be any model. Missing model
access is reported rather than silently substituted. The shared Codex helpers
need Bash and Git (Git Bash on Windows, not the WSL launcher); the selector
and installer need Python 3. The CLI helpers preserve existing permissions.

## Checks

These use temporary repositories and fake CLIs; they do not consume model quota:

```sh
bash tests/test.sh
python3 -m unittest discover -s tests -p 'test_*.py'
```

## License

[MIT](LICENSE)
