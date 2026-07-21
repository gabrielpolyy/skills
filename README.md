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

### [`codex-implement`](./codex-implement)

The inverse division of labor: Claude plans and reviews, `codex` writes the code.
Claude hands codex a concrete spec (`codex exec`, in a workspace-write sandbox — no
network, no commits), reviews the resulting diff itself, and loops valid findings
back through codex as fix rounds until nothing valid remains.

Invoke with `/codex-implement`, typically as "plan X, then /codex-implement".

**Requires** the [`codex`](https://github.com/openai/codex) CLI on your `PATH`.

### [`sde`](./sde)

The full pipeline in one command: the main-loop model (e.g. Fable) plans and writes
a near-final spec, an Opus subagent implements it, the planner reviews the diff and
loops fixes back, and finally the `codex-review` skill runs an external
second-opinion review whose findings get triaged and fixed until clean.

Invoke with `/sde <task>`, e.g. "add retry logic to the uploader /sde".

**Requires** the [`codex-review`](./codex-review) skill (this repo) and the
[`codex`](https://github.com/openai/codex) CLI on your `PATH` for the final review
step.

## Installing a skill

Copy (or symlink) a skill directory into your Claude Code skills folder:

```sh
# personal (all projects)
ln -s "$PWD/codex-review" ~/.claude/skills/codex-review

# or project-scoped
ln -s "$PWD/codex-review" /path/to/project/.claude/skills/codex-review
```

Restart Claude Code (or start a new session) so it picks up the skill.

## License

[MIT](./LICENSE)
