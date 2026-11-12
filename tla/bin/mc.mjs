#!/usr/bin/env node
// Exhaustive breadth-first model checker. Usage: mc.mjs Spec.mjs [maxStates]
// Spec exports: init (state[]), actions {name: s => state[]}, invariants {name: s => bool},
// optional eventually {name: s => bool} (goal must stay reachable from every state),
// optional deadlock = true (a state with no successors is an error).
// Exit: 0 PASS; 1 FAIL (a property is violated); 2 ERROR (bad spec or state limit, not a result).
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

function die(msg) { console.error(`ERROR ${msg}`); process.exit(2); }

if (!process.argv[2]) die('usage: mc.mjs Spec.mjs [maxStates]');
// 388k states of a real spec used 0.9 GB, so the default stays inside Node's heap.
const maxStates = Number(process.argv[3] ?? 1e6);
if (!(maxStates > 0)) die('maxStates must be a positive number');
const spec = await import(pathToFileURL(resolve(process.argv[2])).href);
if (!Array.isArray(spec.init) || spec.init.length === 0) die('init must be a non-empty array');
if (!spec.actions || typeof spec.actions !== 'object') die('actions must be an object of functions');
const invariants = Object.entries(spec.invariants ?? {});
const goals = Object.entries(spec.eventually ?? {});
if (invariants.length === 0 && goals.length === 0 && !spec.deadlock) {
  die('spec checks nothing: export invariants, eventually, or deadlock = true');
}

// States are compared by their JSON text. A value JSON cannot hold (Set, Map, NaN, class
// instance) would turn distinct states into one key and hide them, so it is an error.
function normal(v) {
  if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (Array.isArray(v)) return v.map((x) => normal(x));
  const proto = typeof v === 'object' ? Object.getPrototypeOf(v) : undefined;
  if (proto === Object.prototype || proto === null) {
    return Object.fromEntries(Object.keys(v).sort().filter((k) => v[k] !== undefined).map((k) => [k, normal(v[k])]));
  }
  throw new Error(`a state holds a value that is not plain JSON: ${typeof v === 'object' ? Object.prototype.toString.call(v) : String(v)}`);
}
function key(s, where) {
  try { return JSON.stringify(normal(s)); } catch (e) { return die(`${where}: ${e.message}`); }
}

const seen = new Map(); // key -> { state, parent, action }
const queue = [];
const predecessors = new Map();

for (const s of spec.init) { const k = key(s, 'init'); if (!seen.has(k)) { seen.set(k, { state: s, parent: null, action: 'Init' }); queue.push(k); } }

function trace(k) {
  const out = [];
  for (let n = seen.get(k); n; n = n.parent && seen.get(n.parent)) out.unshift(`${n.action}: ${key(n.state, n.action)}`);
  return out.map((l, i) => `  ${i + 1}. ${l}`).join('\n');
}
function fail(msg, k) { console.log(`FAIL ${msg}\n${trace(k)}\n${seen.size} states explored`); process.exit(1); }

for (let i = 0; i < queue.length; i++) {
  const k = queue[i];
  const { state } = seen.get(k);
  for (const [name, inv] of invariants) if (!inv(state)) fail(`invariant ${name}`, k);
  const next = new Set();
  for (const [name, act] of Object.entries(spec.actions)) {
    const input = structuredClone(state);
    const result = act(input);
    if (result != null && !Array.isArray(result)) {
      die(`action ${name} returned ${typeof result}, expected an array of states ([] means not enabled)\n  state: ${k}`);
    }
    // One clone feeds every successor of this call. A changed input is safe for one
    // successor only; with several, they can share the change (a false PASS).
    if ((result == null || result.length > 1) && key(input, `action ${name}`) !== k) {
      die(result == null
        ? `action ${name} changed its input but returned nothing (missing return?)\n  state: ${k}`
        : `action ${name} changed its input and returned ${result.length} states that can share the change; build each state from a copy ({ ...s } or structuredClone(s))\n  state: ${k}`);
    }
    for (const s2 of result ?? []) {
      const k2 = key(s2, `action ${name}`); next.add(k2);
      if (!predecessors.has(k2)) predecessors.set(k2, new Set());
      predecessors.get(k2).add(k);
      if (!seen.has(k2)) {
        if (seen.size >= maxStates) die(`state limit ${maxStates} reached; cut the constants, or pass a higher limit as the second argument`);
        seen.set(k2, { state: s2, parent: k, action: name }); queue.push(k2);
      }
    }
  }
  if (spec.deadlock && next.size === 0) fail('deadlock', k);
}

for (const [name, goal] of goals) {
  const canReach = new Set([...seen].filter(([, n]) => goal(n.state)).map(([k]) => k));
  const pending = [...canReach];
  for (let i = 0; i < pending.length; i++) {
    for (const k of predecessors.get(pending[i]) ?? []) {
      if (!canReach.has(k)) { canReach.add(k); pending.push(k); }
    }
  }
  for (const k of seen.keys()) if (!canReach.has(k)) fail(`eventually ${name} (goal unreachable from this state)`, k);
}
console.log(`PASS ${seen.size} states, ${Object.keys(spec.actions).length} actions, ${invariants.length} invariants, ${goals.length} goals`);
