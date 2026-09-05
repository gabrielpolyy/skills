"""Behavioral regressions using disposable repositories and offline model CLIs."""
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") or "bash"


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.repo = self.folder / "repo"
        self.repo.mkdir()
        self.prompt = self.folder / "prompt.txt"
        self.git("init", "-q")
        self.env = dict(os.environ, PATH=str(ROOT / "tests/bin") + os.pathsep + os.environ["PATH"],
                        FAKE_CLAUDE_PROMPT_FILE=self.prompt.as_posix(),
                        FAKE_CODEX_PROMPT_FILE=self.prompt.as_posix())
        for key in ("REVIEW_DRY_RUN", "REVIEW_BACKEND", "REVIEW_MODEL", "REVIEW_EFFORT"):
            self.env.pop(key, None)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args])

    def commit_base(self):
        (self.repo / "a.txt").write_text("base\n")
        self.git("add", ".")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.com", "commit", "-qm", "base")

    def review(self, *args, backend="fable", env=None):
        return subprocess.run([BASH, (ROOT / f"{backend}-review/review.sh").as_posix(),
                               *args, "Review requested source", self.repo.as_posix()],
                              env=env or self.env, capture_output=True, text=True, timeout=15)

    def test_canceled_staged_change_is_reviewed_by_both_backends(self):
        self.commit_base()
        (self.repo / "a.txt").write_text("staged\n")
        self.git("add", "a.txt")
        (self.repo / "a.txt").write_text("base\n")
        for backend in ("fable", "astra"):
            r = self.review(backend=backend)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "NO_FINDINGS")
            prompt = self.prompt.read_text()
            if backend == "fable":
                self.assertIn("+staged", prompt)
                self.assertIn("-staged", prompt)
            else:
                self.assertIn("diff --cached", prompt)
                self.assertIn("(unstaged changes", prompt)

    def test_successful_git_conversion_warnings_do_not_pollute_report(self):
        self.git("config", "core.autocrlf", "true")
        self.commit_base()
        (self.repo / "a.txt").write_bytes(b"changed\n")
        for backend in ("fable", "astra"):
            r = self.review(backend=backend)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "NO_FINDINGS")
            self.assertEqual(r.stderr, "")

    def test_unborn_repo_includes_unstaged_edits(self):
        (self.repo / "a.txt").write_text("staged\n")
        self.git("add", "a.txt")
        (self.repo / "a.txt").write_text("current\n")
        self.assertEqual(self.review().returncode, 0)
        self.assertIn("+current", self.prompt.read_text())
        self.assertIn("+staged", self.prompt.read_text())

    def test_invalid_pathspec_fails_before_cli(self):
        self.commit_base()
        for backend in ("fable", "astra"):
            r = self.review("--paths", ":(bogus)a.txt", backend=backend)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("ERROR:", r.stdout)
            self.assertFalse(self.prompt.exists())

    def test_empty_ranges_skip_cli(self):
        self.commit_base()
        for args in (("--range", "HEAD..HEAD"),
                     ("--range", "HEAD..HEAD", "--paths", "absent")):
            r = self.review(*args)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.endswith("NO_CHANGES\n"))
            self.assertFalse(self.prompt.exists())

    def test_binary_and_large_untracked_files_are_explicitly_omitted(self):
        self.commit_base()
        (self.repo / "binary.dat").write_bytes(b"\x00secretbinary\x00")
        (self.repo / "large.txt").write_text("largecontent" * 20000)
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING: review incomplete", r.stdout)
        prompt = self.prompt.read_text()
        self.assertIn("OMITTED:", prompt)
        self.assertIn("binary.dat", prompt)
        self.assertIn("large.txt", prompt)
        self.assertNotIn("secretbinary", prompt)
        self.assertNotIn("largecontent", prompt)
        self.assertLess(len(prompt), 15000)

    def test_large_evidence_finishes_without_quadratic_blank_check(self):
        self.commit_base()
        evidence = self.folder / "evidence.txt"
        evidence.write_text("Evidence claim and measurements.\n" * 4000)
        r = self.review("--evidence", evidence.as_posix())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(evidence.read_text().strip(), self.prompt.read_text())
        self.assertIn(self.git("rev-parse", "--show-toplevel").decode().strip(), self.prompt.read_text())

    def test_audit_reads_clean_repository(self):
        self.commit_base()
        r = self.review("--audit")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "NO_FINDINGS")
        self.assertIn("a.txt", self.prompt.read_text())
        self.assertIn("including existing committed code", self.prompt.read_text())

    def test_audit_path_filter_has_source_scope(self):
        self.commit_base()
        self.assertEqual(self.review("--audit", "--paths", "a.txt").returncode, 0)
        prompt = self.prompt.read_text()
        self.assertIn("Review only source matching", prompt)
        self.assertNotIn("outside this session", prompt)

    def test_nested_untracked_repository_does_not_block_filtered_review(self):
        self.commit_base()
        nested = self.repo / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        (self.repo / "a.txt").write_text("changed\n")
        for backend in ("fable", "astra"):
            r = self.review("--paths", "a.txt", backend=backend)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, "NO_FINDINGS")
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING: review incomplete", r.stdout)
        self.assertIn("not a regular readable file", self.prompt.read_text())

    def test_dangling_symlink_is_reviewed_as_a_link(self):
        self.commit_base()
        try:
            (self.repo / "broken").symlink_to("missing-target")
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Symlink target: missing-target", self.prompt.read_text())

    @unittest.skipIf(os.name == "nt", "POSIX mode bits do not control Windows readability")
    def test_unreadable_untracked_file_is_omitted(self):
        self.commit_base()
        unreadable = self.repo / "unreadable"
        unreadable.write_text("private contents")
        unreadable.chmod(0)
        self.addCleanup(unreadable.chmod, 0o600)
        if os.access(unreadable, os.R_OK):
            self.skipTest("Current user can read files despite mode bits")
        r = self.review()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING: review incomplete", r.stdout)
        self.assertNotIn("private contents", self.prompt.read_text())

    def baseline_material(self):
        # Preserve the documented legacy layout independently of the helper.
        root = self.git("rev-parse", "--show-toplevel").decode().strip()
        return (f"### repo: {root}\n### head: {self.git('rev-parse', 'HEAD').decode().strip()}\n"
                "### status\n").encode() + self.git("status", "--porcelain") + b"### unstaged\n" + self.git("diff") + b"### staged\n" + self.git("diff", "--cached")

    def test_baseline_matching_and_restored_dirty_state(self):
        self.commit_base()
        (self.repo / "a.txt").write_text("before task\n")
        baseline = self.folder / "baseline.txt"
        baseline.write_bytes(self.baseline_material())
        self.assertEqual(self.review("--baseline", baseline.as_posix()).stdout, "NO_CHANGES\n")
        self.assertFalse(self.prompt.exists())
        (self.repo / "a.txt").write_text("base\n")
        self.assertEqual(self.review("--baseline", baseline.as_posix()).stdout, "NO_FINDINGS")

    def test_in_repo_baseline_excludes_itself(self):
        self.commit_base()
        baseline = self.repo / "baseline.txt"
        baseline.write_bytes(self.baseline_material())
        r = self.review("--baseline", baseline.as_posix())
        self.assertEqual(r.stdout, "NO_CHANGES\n", r.stderr)
        self.assertFalse(self.prompt.exists())


if __name__ == "__main__":
    unittest.main()
