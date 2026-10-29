---
name: tla
description: Model-check a user flow or stateful feature TLA+-style (states, actions, invariants, liveness) with a small exhaustive Node checker, no Java. Write a tiny spec of the real code paths, explore every reachable state, and map any counterexample trace back to code. Use for /tla or when a flow (signup, quota, gating, subscription, job lifecycle, retries, two devices) needs a deeper check than reading the code.
---

# Flow model check

Goal: find the interleaving or edge case that code reading misses. The checker explores every reachable state, so keep the model small.

Runner: `node ~/.claude/skills/tla/bin/mc.mjs spec.mjs` (in Codex: `~/.codex/skills/tla/bin/mc.mjs`). Put specs in the project's `specs/` (commit them) or the scratchpad for a one-off.

## Steps

1. **Pick the question.** One sentence: "Can a user ever X without Y?" or "Does every job reach done or failed?". If the user did not give one, propose it before modelling.
2. **Read the real code first.** List the state variables (DB columns, flags, client state), the actions that change them (handlers, crons, client retries, webhooks), and who runs concurrently. Model what the code does, not what the docs say.
3. **Write the spec** from the skeleton below. Rules:
   - Keep constants small: 1 to 2 users, 2 to 3 items, counters bounded.
   - One action per real code path. Include failure paths: timeout, duplicate request, retry, cron firing mid-flow, second device.
   - `invariants` = what must never hold. `eventually` = a goal that must stay reachable from every state (a flow that can get stuck or loop away from it fails).
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

- `init`: array of start states (plain JSON-able objects).
- `actions`: name → function from a state to an array of next states (empty array = not enabled). The checker passes a deep clone, so mutating and returning `[s]` is fine.
- `invariants`, `eventually`: name → predicate.

## Pitfalls

- `eventually` is "goal reachable from every state" (AG EF), weaker than TLC's fairness-based liveness. A flow that *can* progress passes even if nothing forces it. For "must happen", also bound the number of retries so stalling runs out.
- State explosion: cut constants before cutting actions. 10^5 states runs in seconds in Node; 10^7 does not.
- Guards that return `false` instead of `[]` turn into a bogus state. Use the `each` helper or `|| []`.
- Time-based rules (daily quota reset, expiry) become an explicit `Tick` action with a bounded clock.
- No local dev DB in vt: never "verify" the model by writing to prod. Verify against code and tests.
