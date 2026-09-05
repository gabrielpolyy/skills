import contextlib
import importlib.util
import io
import os
import re
import subprocess
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).resolve().parents[1] / "scripts/install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def link_directory(link, target):
    if os.name == "nt":
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.dest = Path(self.temp.name) / "skills"
        self.dest.mkdir()
        for name in installer.CURRENT:
            folder = self.repo / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(name)

    def assert_installed(self, dest):
        for name in installer.CURRENT:
            self.assertEqual((dest / name / "SKILL.md").read_text(), name)

    def test_installs_and_is_idempotent(self):
        installer.install(self.repo, [self.dest])
        installer.install(self.repo, [self.dest])
        self.assert_installed(self.dest)

    def test_removes_only_owned_retired_links(self):
        old = self.repo / installer.RETIRED[0]
        old.mkdir()
        (old / "keep.txt").write_text("preserved")
        link_directory(self.dest / old.name, old)
        installer.install(self.repo, [self.dest])
        self.assertFalse(os.path.lexists(self.dest / old.name))
        self.assertEqual((old / "keep.txt").read_text(), "preserved")

    def test_upgrade_removes_dangling_retired_links(self):
        # The real upgrade: `git pull` already deleted the retired folders, so
        # the old links dangle. They must still be recognized as ours and removed.
        for name in installer.RETIRED:
            self.assertFalse((self.repo / name).exists())
            link_directory(self.dest / name, self.repo / name)
        installer.install(self.repo, [self.dest])
        for name in installer.RETIRED:
            self.assertFalse(os.path.lexists(self.dest / name))
        self.assert_installed(self.dest)

    def test_dangling_link_elsewhere_is_preserved(self):
        old = self.dest / installer.RETIRED[0]
        link_directory(old, Path(self.temp.name) / "elsewhere" / installer.RETIRED[0])
        with self.assertRaises(ValueError):
            installer.install(self.repo, [self.dest])
        self.assertTrue(os.path.lexists(old))
        self.assertFalse((self.dest / "sol-review").exists())

    def test_conflict_changes_nothing(self):
        (self.dest / "fable-review").mkdir()
        with self.assertRaises(ValueError):
            installer.install(self.repo, [self.dest])
        self.assertFalse((self.dest / "sol-review").exists())

    def test_unrelated_retired_link_is_preserved(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        old = self.dest / installer.RETIRED[0]
        link_directory(old, other)
        with self.assertRaises(ValueError):
            installer.install(self.repo, [self.dest])
        self.assertEqual(old.resolve(), other.resolve())

    def test_installs_into_every_destination_and_creates_missing_ones(self):
        second = Path(self.temp.name) / "missing" / "skills"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            installer.install(self.repo, [self.dest, second])
        self.assert_installed(self.dest)
        self.assert_installed(second)
        verified = [line for line in out.getvalue().splitlines() if line.startswith("Verified ")]
        self.assertEqual(verified, [f"Verified {', '.join(installer.CURRENT)} in {d}"
                                    for d in (self.dest, second)])

    def test_failing_second_destination_leaves_the_first_untouched(self):
        second = Path(self.temp.name) / "second"
        second.mkdir()
        (second / "fable-review").mkdir()   # unrelated skill: must not be replaced
        with self.assertRaisesRegex(ValueError, re.escape(str(second / "fable-review"))):
            installer.install(self.repo, [self.dest, second])
        self.assertEqual(os.listdir(self.dest), [])
        self.assertEqual(os.listdir(second), ["fable-review"])

    def test_second_destination_that_is_a_file_fails_before_any_change(self):
        second = Path(self.temp.name) / "second"
        second.write_text("not a directory")
        with self.assertRaisesRegex(ValueError, re.escape(str(second))):
            installer.install(self.repo, [self.dest, second])
        self.assertEqual(os.listdir(self.dest), [])
        self.assertEqual(second.read_text(), "not a directory")

    def test_second_destination_under_a_file_fails_before_any_change(self):
        parent = Path(self.temp.name) / "parent"
        parent.write_text("not a directory")
        with self.assertRaisesRegex(ValueError, re.escape(str(parent))):
            installer.install(self.repo, [self.dest, parent / "skills"])
        self.assertEqual(os.listdir(self.dest), [])
        self.assertEqual(parent.read_text(), "not a directory")

    def test_destination_through_a_directory_symlink_is_accepted(self):
        real = Path(self.temp.name) / "real"
        real.mkdir()
        link = Path(self.temp.name) / "link"
        link_directory(link, real)
        installer.install(self.repo, [link / "skills"])
        self.assert_installed(real / "skills")


class CommandLineTests(unittest.TestCase):
    """The real repository is linked into a fake home; nothing outside it is touched."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        original = installer.Path.home
        installer.Path.home = classmethod(lambda cls: self.home)
        self.addCleanup(setattr, installer.Path, "home", original)

    def run_main(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            installer.main(argv)

    def test_default_installs_for_claude_code_and_codex(self):
        self.run_main([])
        for cli in (".claude", ".codex"):
            for name in installer.CURRENT:
                self.assertTrue((self.home / cli / "skills" / name / "SKILL.md").is_file(), cli)

    def test_repeated_skills_dir_installs_only_there(self):
        first = Path(self.temp.name) / "one"
        second = Path(self.temp.name) / "two"
        self.run_main(["--skills-dir", str(first), "--skills-dir", str(second)])
        for dest in (first, second):
            for name in installer.CURRENT:
                self.assertTrue((dest / name / "SKILL.md").is_file())
        self.assertEqual(os.listdir(self.home), [])


if __name__ == "__main__":
    unittest.main()
