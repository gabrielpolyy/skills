"""Validate discoverable skills and their local resources."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SKILLS = ("sol-review", "astra-review", "fable-review")
SKILLS = (*REVIEW_SKILLS, "app-store-release", "tla", "wf")

class SkillFileTests(unittest.TestCase):
    def test_expected_skills_are_discoverable(self):
        self.assertEqual(sorted(p.parent.name for p in ROOT.glob("*/SKILL.md")), sorted(SKILLS))
        for skill in SKILLS:
            text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith(f"---\nname: {skill}\ndescription: "))
            if skill in REVIEW_SKILLS:
                self.assertIn(f"/{skill}", text.split("---", 2)[1])

    def test_review_skills_differ_only_in_reviewer_lines(self):
        def read(skill):
            wrapper = (ROOT / skill / "review.sh").read_text(encoding="utf-8")
            pins = dict(re.findall(r"^export REVIEW_(BACKEND|MODEL|EFFORT)=(\S+)$", wrapper, re.M))
            return pins, (ROOT / skill / "SKILL.md").read_text(encoding="utf-8").splitlines()

        reference = read(REVIEW_SKILLS[0])[1]
        for skill in REVIEW_SKILLS:
            pins, lines = read(skill)
            self.assertIn(f"**{pins['MODEL']} at {pins['EFFORT']}**", "\n".join(lines))
            own = (skill, skill.split("-")[0].capitalize(), pins["MODEL"], pins["BACKEND"])
            self.assertEqual(len(lines), len(reference), skill)
            for number, (line, expected) in enumerate(zip(lines, reference), 1):
                if line != expected:
                    self.assertTrue(any(token in line for token in own),
                                    f"{skill}/SKILL.md:{number} drifted: {line}")

    def test_relative_links_resolve(self):
        for path in [ROOT / skill / "SKILL.md" for skill in SKILLS] + [ROOT / "README.md"]:
            for target in re.findall(r"\]\(([^)#]+)\)", path.read_text(encoding="utf-8")):
                if "://" not in target:
                    self.assertTrue((path.parent / target).is_file(), f"{path}: {target}")

if __name__ == "__main__":
    unittest.main()
