---
name: wf
description: Run the current task as a Workflow of up to N parallel Claude Opus 5.5 agents (default 5) when the task warrants it, otherwise do it inline; then run /astra-review on the result. Use for /wf, /wf <N>, or /wf <N> <task>. Invoking this skill is the user's explicit opt-in to multi-agent orchestration.
---

# wf: up to N Opus agents, then Astra review

Arguments: `[N] [task]`. `N` is an integer agent count. The rest is the task. If no task text is given, use the task from the current conversation.

- Explicit `N` (`/wf 5`) means exactly N agents if the Workflow runs. Do not reduce the count.
- No `N` means up to 5 agents. Use only as many as the task needs.

Invoking this skill is the explicit opt-in the Workflow tool requires. Do not ask for confirmation.

## Step 0: Decide whether this skill fits the case

The user offers orchestration; you judge whether it helps. Discard the skill when any of these holds:

- The task touches one or two files and you would finish it in a few tool calls.
- The task is a lookup, a question, or a one-line fix.
- The parts depend on each other, so parallel agents would only wait on or conflict with one another.
- You are unsure what the task is; orchestration multiplies a wrong reading.

If you discard it: say in one line that you skipped /wf and why, then do the task as you normally would. Ignore the rest of this skill.

## Step 1: Scope the work inline

Find the work-list yourself: files to touch, modules involved, tests that must pass. Keep this short; the agents do the work.

Split the task into work units, at most N:

- If the task decomposes into independent parts, assign one part per agent. Do not pad with filler units; with an explicit `N`, pad only by splitting the largest parts further or by assigning the remaining agents as verifiers (tests, edge cases, docs) for the others' parts.
- If the task does not decompose (one bug, one design), run independent attempts from different angles and judge them in Step 3. Without an explicit `N`, 2 or 3 attempts are usually enough.

## Step 2: Run the Workflow

Load the `workflow-authoring` skill, then call the Workflow tool with an inline script. Rules for the script:

- One `agent()` call per work unit in the main phase (exactly N with an explicit `N`), all with `model: 'opus'` (Claude Opus 5.5). Never omit the model: the agents must not inherit the session model.
- Set `meta.phases[].model: 'opus'` for that phase.
- Use `parallel()` for the units; they are independent.
- Use `isolation: 'worktree'` only when agents edit the same files in parallel. When one agent owns one file set, keep them in the main tree.
- Give each agent its unit, the file list, the tests to run, and a schema that returns `{ files: string[], summary: string, tests: string }`.
- `log()` what each agent returned.

Script shape:

```js
export const meta = {
  name: 'wf',
  description: 'Parallel Opus agents on one task',
  phases: [{ title: 'Work', model: 'opus' }],
}
const UNITS = args.units
const SCHEMA = { type: 'object', properties: {
  files: { type: 'array', items: { type: 'string' } },
  summary: { type: 'string' }, tests: { type: 'string' } },
  required: ['files', 'summary', 'tests'] }
const results = await parallel(UNITS.map((u, i) => () =>
  agent(u.prompt, { label: `work:${i + 1}`, phase: 'Work', model: 'opus', schema: SCHEMA })))
return results.filter(Boolean)
```

Pass the units through `args` as a real JSON array, not a string.

## Step 3: Integrate

Read the results. If the units were independent parts, confirm they merge: run the project tests once. If the units were attempts, pick the best on test evidence and discard the others (revert their edits or drop their worktrees). Fix integration conflicts yourself.

## Step 4: Astra review

Invoke the `astra-review` skill on the task's delta (the files the agents reported plus your integration edits). Follow that skill's loop to completion: every finding fixed or discarded with evidence.

## Step 5: Report

One short message: what the agents did, test result, Astra review outcome, files changed. Do not commit, push or deploy.
