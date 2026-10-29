---
name: tla
description: Model-check a user flow or stateful feature TLA+-style with a small exhaustive Node checker, no Java. Check invariants and goal reachability in a bounded model of real code paths. Map counterexamples back to code. Use for /tla or stateful flows with concurrency, retries, or stuck jobs.
---

# Flow model check

Goal: find the interleaving or edge case that code reading misses. The checker explores every reachable model state, so keep the model small. A pass applies only to the model's bounds and assumptions.

Runner: `node ~/.claude/skills/tla/bin/mc.mjs spec.mjs` (in Codex: `~/.codex/skills/tla/bin/mc.mjs`). Put specs in the project's `specs/` (commit them) or the scratchpad for a one-off.

## Step 0: Decide whether a model check is needed

The user offers the check; you judge whether it pays off. Skip the skill when any of these holds:

- The question is answered by reading the code: one handler, one path, no concurrency.
- The flow has no state that persists between calls, or no interleaving (no retries, crons, webhooks, second device, concurrent users).
- The user asks for a code review, a test, or a fix, not for an exhaustive check.
- You cannot name the question in one sentence; a model of an unclear question proves nothing.

Use the skill when the flow has at least 2 actors or actions that can interleave, and a wrong interleaving would cost something (money, data, access, a stuck job).

If you skip it: say in one line that you skipped /tla and why, then answer the question by reading the code. Ignore the rest of this skill.

## Steps

1. **Pick the question.** Use one sentence: "Can a user ever X without Y?" or "Can every job still reach done or failed?". If the user requires guaranteed completion, state that this checker cannot prove it. If the user did not give a question, propose it before modelling.
2. **Read the real code first.** List the state variables (DB columns, flags, client state), the actions that change them (handlers, crons, client retries, webhooks), and who runs concurrently. Model what the code does, not what the docs say.
3. **Write the spec** from the skeleton below. Rules:
   - Keep constants small: 1 to 2 users, 2 to 3 items, counters bounded.
   - Model each atomic step as an action. Split handlers where another actor can change shared state between operations. Store each actor's step and local values in the state. For example, separate a quota read from its write unless the code makes them atomic. Include timeouts, duplicate requests, retries, crons, and second devices where relevant.
   - `invariants` predicates must return true in every reachable state.
   - `eventually` goals must remain reachable from every state. A cycle with an exit to the goal passes, even if execution can loop forever.
   - Name assumptions in a comment block at the top of the spec.
4. **Run** the checker. Exit 0 prints `PASS <states>`. Exit 1 prints the failed property and the numbered trace from `Init`.
5. **Read the trace** state by state. Map each step to a file:line in the code. Decide: real bug, or model too loose? If the model is too loose, tighten it and rerun. Never weaken the property to make it pass.
6. **Report**: the question, the model's assumptions, the result, the trace as a numbered list with code pointers, and the fix or the next check. If a bug is confirmed, add a regression test in the code too; the spec is not the test.

## Spec format (ES module)

```js
const USERS = ['u1', 'u2'], MAX = 2;
export const init = [{ state: { u1: 'new', u2: 'new' }, credits: { u1: 0, u2: 0 } }];
const each = (f) => (s) => USERS.flatMap((u) => f(s, u) || []);   // guard && [next] per user
export const actions = {
  Signup: each((s, u) => s.state[u] === 'new' && [{ ...s, state: { ...s.state, [u]: 'active' } }]),
  Grant:  each((s, u) => s.state[u] === 'active' && s.credits[u] < MAX
                         && [{ ...s, credits: { ...s.credits, [u]: s.credits[u] + 1 } }]),
};
export const invariants = { NoCreditBeforeSignup: (s) => USERS.every((u) => s.credits[u] === 0 || s.state[u] === 'active') };
export const eventually = { AllActive: (s) => USERS.every((u) => s.state[u] === 'active') };
export const deadlock = false;   // true: a state with no successor is an error
```

- `init`: non-empty array of start states (plain JSON-able objects).
- `actions`: name → function from a state to an array of next states (empty array = not enabled). The checker passes a deep clone, so mutating and returning `[s]` is fine.
- `invariants`, `eventually`: name → predicate.

## Pitfalls

- `eventually` checks goal reachability (AG EF), not guaranteed progress or fairness. A retry bound removes possible runs; it does not prove completion without that bound. Use a temporal model checker if the question requires guaranteed progress.
- State explosion: cut constants before cutting actions. Runtime and memory depend on both states and transitions.
- Guards that return `false` instead of `[]` cause an error. Use the `each` helper or `|| []`.
- Time-based rules (daily quota reset, expiry) become an explicit `Tick` action with a bounded clock.
- No local dev DB in vt: never "verify" the model by writing to prod. Verify against code and tests.
