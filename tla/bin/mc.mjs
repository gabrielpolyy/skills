#!/usr/bin/env node
// Exhaustive breadth-first model checker. Usage: mc.mjs Spec.mjs
// Spec exports: init (state[]), actions {name: s => state[]}, invariants {name: s => bool},
// optional eventually {name: s => bool} (goal must stay reachable from every state),
// optional deadlock = true (a state with no successors is an error).
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const spec = await import(pathToFileURL(resolve(process.argv[2])).href);
const sorted = (v) => v && typeof v === 'object' && !Array.isArray(v) ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v;
const key = (s) => JSON.stringify(sorted(s));
const seen = new Map(); // key -> { state, parent, action }
const queue = [];
const succ = new Map(); // key -> set of successor keys

for (const s of spec.init) { const k = key(s); if (!seen.has(k)) { seen.set(k, { state: s, parent: null, action: 'Init' }); queue.push(k); } }

function trace(k) {
  const out = [];
  for (let n = seen.get(k); n; n = n.parent && seen.get(n.parent)) out.unshift(`${n.action}: ${key(n.state)}`);
  return out.map((l, i) => `  ${i + 1}. ${l}`).join('\n');
}
function fail(msg, k) { console.log(`FAIL ${msg}\n${trace(k)}\n${seen.size} states explored`); process.exit(1); }

while (queue.length) {
  const k = queue.shift();
  const { state } = seen.get(k);
  for (const [name, inv] of Object.entries(spec.invariants ?? {})) if (!inv(state)) fail(`invariant ${name}`, k);
  const next = new Set();
  for (const [name, act] of Object.entries(spec.actions)) {
    for (const s2 of act(structuredClone(state)) ?? []) {
      const k2 = key(s2); next.add(k2);
      if (!seen.has(k2)) { seen.set(k2, { state: s2, parent: k, action: name }); queue.push(k2); }
    }
  }
  if (spec.deadlock && next.size === 0) fail('deadlock', k);
  succ.set(k, next);
}

for (const [name, goal] of Object.entries(spec.eventually ?? {})) {
  const canReach = new Set([...seen].filter(([, n]) => goal(n.state)).map(([k]) => k));
  let grew = true;
  while (grew) { grew = false; for (const [k, ns] of succ) if (!canReach.has(k) && [...ns].some((n) => canReach.has(n))) { canReach.add(k); grew = true; } }
  for (const k of seen.keys()) if (!canReach.has(k)) fail(`eventually ${name} (goal unreachable from this state)`, k);
}
console.log(`PASS ${seen.size} states, ${Object.keys(spec.actions).length} actions`);
