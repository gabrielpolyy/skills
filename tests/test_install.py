import importlib.util
import os
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

    def test_installs_and_is_idempotent(self):
        installer.install(self.repo, self.dest)
        installer.install(self.repo, self.dest)
        for name in installer.CURRENT:
            self.assertEqual((self.dest / name / "SKILL.md").read_text(), name)

    def test_removes_only_owned_retired_links(self):
        old = self.repo / installer.RETIRED[0]
        old.mkdir()
        (old / "keep.txt").write_text("preserved")
        link_directory(self.dest / old.name, old)
        installer.install(self.repo, self.dest)
        self.assertFalse(os.path.lexists(self.dest / old.name))
        self.assertEqual((old / "keep.txt").read_text(), "preserved")

    def test_conflict_changes_nothing(self):
        (self.dest / "scientific").mkdir()
        with self.assertRaises(ValueError):
            installer.install(self.repo, self.dest)
        self.assertFalse((self.dest / "low").exists())

    def test_unrelated_retired_link_is_preserved(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        old = self.dest / installer.RETIRED[0]
        link_directory(old, other)
        with self.assertRaises(ValueError):
            installer.install(self.repo, self.dest)
        self.assertEqual(old.resolve(), other.resolve())


if __name__ == "__main__":
    unittest.main()
