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

Delegate an implementation to an external builder: `codex exec` (in a workspace-write
sandbox — repo writes only, no network, no commits) implements a self-contained spec
in the current repo and runs the tests; Claude then verifies the delta against the
brief. The inverse of `codex-review`.

Invoke with `/codex-implement <task>`, or ask Claude to "have codex implement this".

**Requires** the [`codex`](https://github.com/openai/codex) CLI on your `PATH`.

### [`sde-fable-opus-sol`](./sde-fable-opus-sol)

The full pipeline in one command: Fable (the main loop) plans and writes a
near-final spec, an Opus subagent implements it, Fable checks the delta against
the spec, the `codex-review` skill runs an external second-opinion review whose
findings get triaged and fixed until clean, and an Opus subagent verifies
user-facing changes end-to-end in the running app. Refuses to run if the
session model isn't Fable (use `sde-opus-sol` instead).

Invoke with `/sde-fable-opus-sol <task>`, e.g. "add retry logic to the uploader
/sde-fable-opus-sol".

**Requires** the [`codex-review`](./codex-review) skill (this repo) and the
[`codex`](https://github.com/openai/codex) CLI on your `PATH` for the final review
step.

### [`sde-fable-codex`](./sde-fable-codex)

The pipeline with the roles swapped at the build step — Fable designs, codex
implements: Fable (the main loop) plans and writes the near-final spec, the
`codex-implement` skill has codex build it in a workspace-write sandbox, Fable
reviews the delta against the spec (the pipeline's cross-model review, since codex
also runs the external `codex-review` pass), and an Opus subagent verifies
user-facing changes end-to-end in the running app. Refuses to run if the session
model isn't Fable.

Invoke with `/sde-fable-codex <task>`.

**Requires** the [`codex-implement`](./codex-implement) and
[`codex-review`](./codex-review) skills (this repo) and the
[`codex`](https://github.com/openai/codex) CLI on your `PATH` — codex is the builder
in this variant.

### [`sde-opus-sol`](./sde-opus-sol)

The same pipeline on a fixed model budget — no Fable anywhere: Opus (the main
loop) plans and writes the spec, an Opus subagent implements it, the
`codex-review` skill (Sol at high reasoning effort) is the pipeline's code
reviewer, and an Opus subagent verifies user-facing changes end-to-end in the
running app. Refuses to run if the session model isn't Opus.

Invoke with `/sde-opus-sol <task>`.

**Requires** the [`codex-review`](./codex-review) skill (this repo) and the
[`codex`](https://github.com/openai/codex) CLI on your `PATH` — codex is the
only code reviewer in this variant.

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
