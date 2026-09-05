"""Validate discoverable skills and their local resources."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("sol-review", "astra-review", "fable-review")

class SkillFileTests(unittest.TestCase):
    def test_only_review_skills_are_discoverable(self):
        self.assertEqual(sorted(p.parent.name for p in ROOT.glob("*/SKILL.md")), sorted(SKILLS))
        for skill in SKILLS:
            text = (ROOT / skill / "SKILL.md").read_text()
            self.assertTrue(text.startswith(f"---\nname: {skill}\ndescription: "))
            self.assertIn(f"/{skill}", text.split("---", 2)[1])

    def test_relative_links_resolve(self):
        for path in [ROOT / skill / "SKILL.md" for skill in SKILLS] + [ROOT / "README.md"]:
            for target in re.findall(r"\]\(([^)#]+)\)", path.read_text()):
                if "://" not in target:
                    self.assertTrue((path.parent / target).is_file(), f"{path}: {target}")

if __name__ == "__main__":
    unittest.main()
