# useful-skills

A small collection of [Claude Code](https://claude.com/claude-code) skills I use.

## Skills

### [`codex-review`](./codex-review)

Have an external reviewer (`codex exec`, in a read-only sandbox) review what changed
in the current session, then triage and fix the valid findings — iterating until codex
is clean or the only remaining findings aren't worth acting on.

Invoke with `/codex-review`, or ask Claude to "review the current changes with codex"
right after implementing something.

**Requires** the [`codex`](https://github.com/openai/codex) CLI on your `PATH`.

## Installing a skill

Copy (or symlink) a skill directory into your Claude Code skills folder:

```sh
# personal (all projects)
ln -s "$PWD/codex-review" ~/.claude/skills/codex-review

# or project-scoped
ln -s "$PWD/codex-review" /path/to/project/.claude/skills/codex-review
```

Restart Claude Code (or start a new session) so it picks up the skill.
