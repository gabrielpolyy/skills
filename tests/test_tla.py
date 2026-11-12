from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModelCheckerTests(unittest.TestCase):
    def run_spec(self, source, *args):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.mjs"
            path.write_text(source, encoding="utf-8")
            return subprocess.run(
                ["node", str(ROOT / "tla/bin/mc.mjs"), str(path), *args],
                capture_output=True, text=True, timeout=10)

    def assert_rejected(self, result, message):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("PASS", result.stdout)
        self.assertIn(message, result.stderr)

    def test_empty_model_is_rejected(self):
        result = self.run_spec("export const init=[]; export const actions={};")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PASS", result.stdout)
        self.assertIn("init must be a non-empty array", result.stderr)

    def test_invariant_failure_has_shortest_trace(self):
        result = self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>s.n<2?[{n:s.n+1}]:[]};
export const invariants={BelowTwo:s=>s.n<2};
""")
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL invariant BelowTwo', result.stdout)
        self.assertIn('1. Init: {"n":0}', result.stdout)
        self.assertIn('3. Step: {"n":2}', result.stdout)

    def test_deadlock_is_reported(self):
        result = self.run_spec("""
export const init=[{}]; export const actions={}; export const deadlock=true;
""")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL deadlock", result.stdout)

    def test_loop_with_exit_passes_reachability(self):
        result = self.run_spec("""
export const init=[{done:false}];
export const actions={Wait:s=>[s],Finish:s=>[{done:true}]};
export const eventually={Done:s=>s.done};
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS 2 states", result.stdout)

    def test_trapped_cycle_fails_reachability(self):
        result = self.run_spec("""
export const init=[{n:0}];
export const actions={Branch:s=>s.n===0?[{n:1},{n:2}]:[],Loop:s=>s.n===2?[s]:[]};
export const eventually={Done:s=>s.n===1};
""")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL eventually Done", result.stdout)
        self.assertIn('2. Branch: {"n":2}', result.stdout)

    def test_each_goal_is_checked_from_every_initial_state(self):
        result = self.run_spec("""
export const init=[{n:0},{n:1}]; export const actions={};
export const eventually={Always:()=>true,Zero:s=>s.n===0};
""")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL eventually Zero", result.stdout)
        self.assertIn('1. Init: {"n":1}', result.stdout)

    def test_long_chain_completes(self):
        result = self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>s.n<50000?[{n:s.n+1}]:[]};
export const eventually={Done:s=>s.n===50000};
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS 50001 states", result.stdout)

    def test_missing_spec_argument_is_rejected(self):
        result = subprocess.run(["node", str(ROOT / "tla/bin/mc.mjs")],
                                capture_output=True, text=True, timeout=10)
        self.assert_rejected(result, "usage:")

    def test_missing_actions_are_rejected(self):
        self.assert_rejected(self.run_spec("export const init=[{}]; export const deadlock=true;"),
                             "actions must be an object")

    def test_spec_that_checks_nothing_is_rejected(self):
        # A misspelled export must not pass as a checked goal.
        self.assert_rejected(self.run_spec("""
export const init=[{n:0}]; export const actions={};
export const eventualy={Done:()=>false};
"""), "checks nothing")

    def test_set_valued_state_is_rejected(self):
        # JSON turns every Set into {}, which would merge distinct states into one.
        self.assert_rejected(self.run_spec("""
export const init=[{held:new Set()}];
export const actions={Take:s=>s.held.size<2?[{held:new Set([...s.held,'x'+s.held.size])}]:[]};
export const invariants={AtMostOne:s=>s.held.size<=1};
"""), "not plain JSON")

    def test_object_key_order_inside_arrays_does_not_split_states(self):
        result = self.run_spec("""
export const init=[{items:[{a:1,b:2}]}];
export const actions={Flip:()=>[{items:[{b:2,a:1}]}]};
export const invariants={One:s=>s.items.length===1};
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS 1 states", result.stdout)

    def test_mutated_input_shared_by_two_successors_is_rejected(self):
        # Without the check this prints PASS 2 states: both users change one object.
        self.assert_rejected(self.run_spec("""
const USERS=['u1','u2'];
const each=f=>s=>USERS.flatMap(u=>f(s,u)||[]);
export const init=[{u1:'new',u2:'new'}];
export const actions={Signup:each((s,u)=>{ if(s[u]!=='new') return []; s[u]='active'; return [s]; })};
export const invariants={NeverExactlyOne:s=>(s.u1==='active')===(s.u2==='active')};
"""), "changed its input")

    def test_mutating_one_successor_still_works(self):
        result = self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>{ if(s.n>=2) return []; s.n++; return [s]; }};
export const invariants={Bounded:s=>s.n<=2};
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS 3 states", result.stdout)

    def test_missing_return_after_mutation_is_rejected(self):
        self.assert_rejected(self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>{ s.n++; }};
export const invariants={Zero:s=>s.n===0};
"""), "returned nothing")

    def test_guard_that_returns_nothing_means_not_enabled(self):
        result = self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>{ if(s.n<2) return [{n:s.n+1}]; }};
export const invariants={Bounded:s=>s.n<=2};
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS 3 states", result.stdout)

    def test_guard_that_returns_false_is_rejected(self):
        self.assert_rejected(self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>s.n<2&&[{n:s.n+1}]};
export const invariants={Bounded:s=>s.n<=2};
"""), "expected an array")

    def test_state_limit_stops_an_unbounded_model(self):
        self.assert_rejected(self.run_spec("""
export const init=[{n:0}];
export const actions={Step:s=>[{n:s.n+1}]};
export const invariants={Any:()=>true};
""", "100"), "state limit 100")


if __name__ == "__main__":
    unittest.main()
