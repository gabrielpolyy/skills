from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ModelCheckerTests(unittest.TestCase):
    def run_spec(self, source):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.mjs"
            path.write_text(source, encoding="utf-8")
            return subprocess.run(
                ["node", str(ROOT / "tla/bin/mc.mjs"), str(path)],
                capture_output=True, text=True, timeout=10)

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


if __name__ == "__main__":
    unittest.main()
