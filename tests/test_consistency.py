"""Drift protection: the role matrix in shared/workflow.md is canonical."""

import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ("low", "high", "scientific")
SKILLS = PROFILES + ("sol-review",)
MODELS = ("Sol", "Opus", "Astra", "Fable")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PAIR = re.compile(r"\b(Sol|Opus|Astra|Fable)\s+\**(low|medium|high|xhigh|max)\**\b")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def table_rows(text, first_header):
    """Rows of the Markdown table whose header starts with first_header."""
    rows, inside = [], False
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] == first_header:
            inside = True
            continue
        if inside and line.startswith("|"):
            if not set(cells[0]) <= set("-: "):
                rows.append(cells)
        elif inside:
            break
    return rows


def matrix():
    """{role: {"id": ..., "default": effort, "plan_scientific": effort}}"""
    result = {}
    for role, ident, effort in table_rows(read("shared/workflow.md"), "Role model"):
        every = re.match(r"(\w+) for every role", effort)
        split = re.match(r"(\w+) (?:ONLY )?for scientific planning; (\w+) otherwise", effort)
        if every:
            default = plan = every.group(1)
        elif split:
            plan, default = split.groups()
        else:
            raise AssertionError(f"unparsed effort cell: {effort}")
        result[role] = {"id": ident.strip("`"), "default": default, "plan_scientific": plan}
    return result


def allowed(role, effort, table, profile, stage):
    """Is this model/effort pair consistent with the matrix for that stage?"""
    entry = table[role]
    if effort == entry["default"]:
        return True
    return profile == "scientific" and stage == "Plan" and effort == entry["plan_scientific"]


def load_selector():
    spec = importlib.util.spec_from_file_location("routing", ROOT / "scripts/choose-builder.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.table = matrix()
        self.assertEqual(sorted(self.table), sorted(MODELS))

    def test_selector_efforts_and_pools_match_matrix(self):
        routing = load_selector()
        expected = {role.lower(): entry["default"] for role, entry in self.table.items()}
        self.assertEqual(routing.EFFORT, expected)
        for profile in PROFILES:
            rows = {row[0]: row[1] for row in table_rows(read(f"{profile}/SKILL.md"), "Stage")}
            builders = tuple(role.lower() for role, _ in PAIR.findall(rows["Implement"]))
            self.assertEqual(routing.POOLS[profile], builders, profile)
        high_plan = {row[0]: row[1] for row in table_rows(read("high/SKILL.md"), "Stage")}["Plan"]
        planners = tuple(role.lower() for role, _ in PAIR.findall(high_plan))
        self.assertEqual(routing.POOLS["planner"], planners)

    def test_high_plans_with_one_model_and_scientific_with_both(self):
        """High selects a single planner ("OR"); scientific still plans with both ("+")."""
        high = {row[0]: row[1] for row in table_rows(read("high/SKILL.md"), "Stage")}
        self.assertEqual(high["Plan"], "Astra medium OR Fable high, selected by remaining quota")
        self.assertIn("NOT used for planning", high["Review"])
        scientific = {row[0]: row[1] for row in table_rows(read("scientific/SKILL.md"), "Stage")}
        self.assertEqual(scientific["Plan"], "Astra high + Fable xhigh")
        readme = {re.search(r"/(\w+)`", row[0]).group(1): row for row in table_rows(read("README.md"), "Skill")}
        self.assertEqual(readme["high"][1], "Astra **medium** or Fable **high**")
        self.assertIn("+", readme["scientific"][1])
        for text in (read("high/SKILL.md"), read("README.md")):
            self.assertNotIn("Both models must contribute", text)
        self.assertIn("--choose planner", read("high/SKILL.md"))

    def test_helper_defaults_and_pins_exist_in_matrix(self):
        ids = {entry["id"]: role for role, entry in self.table.items()}
        for script, prefix in (("scripts/implement.sh", "IMPLEMENT"), ("scripts/review.sh", "REVIEW")):
            text = read(script)
            models = re.findall(prefix + r"_MODEL:=([^}]+)}", text)
            efforts = re.findall(prefix + r"_EFFORT:=([^}]+)}", text)
            self.assertEqual(len(models), 2, script)   # one default per backend
            for model, effort in zip(models, efforts):
                self.assertIn(model, ids, script)
                self.assertEqual(effort, self.table[ids[model]]["default"], script)
        text = read("sol-review/review.sh")
        model = re.search(r"REVIEW_MODEL=(\S+)", text).group(1)
        effort = re.search(r"REVIEW_EFFORT=(\S+)", text).group(1)
        self.assertIn(model, ids)
        self.assertEqual(effort, self.table[ids[model]]["default"])
        self.assertIn("REVIEW_BACKEND=codex", text)

    def test_profile_tables_and_readme_agree_with_matrix(self):
        for profile in PROFILES:
            rows = table_rows(read(f"{profile}/SKILL.md"), "Stage")
            self.assertEqual(rows[0][0], "Coordinate", profile)   # recommended, not required
            for stage, cell in rows:
                pairs = PAIR.findall(cell)
                if stage not in ("Review", "Coordinate"):   # these rows may name no pair
                    self.assertTrue(pairs, f"{profile} {stage} names no model/effort")
                for role, effort in pairs:
                    self.assertTrue(allowed(role, effort, self.table, profile, stage),
                                    f"{profile}/SKILL.md {stage}: {role} {effort}")
        readme_rows = table_rows(read("README.md"), "Skill")
        self.assertEqual(len(readme_rows), len(PROFILES))
        for skill, plan, implement, review in readme_rows:
            profile = re.search(r"/(\w+)`", skill).group(1)
            for stage, cell in (("Plan", plan), ("Implement", implement), ("Review", review)):
                for role, effort in PAIR.findall(cell):
                    self.assertTrue(allowed(role, effort, self.table, profile, stage),
                                    f"README {profile} {stage}: {role} {effort}")

    def test_scientific_orchestrator_requirement_is_stated_consistently(self):
        """Only scientific requires its orchestrator; the shared prose must not deny it."""
        coordinate = {}
        for profile in PROFILES:
            coordinate[profile] = table_rows(read(f"{profile}/SKILL.md"), "Stage")[0][1]
        self.assertTrue(coordinate["scientific"].startswith("REQUIRED"))
        for profile in ("low", "high"):
            self.assertFalse(coordinate[profile].startswith("REQUIRED"), profile)

        def sentences(path):
            return re.split(r"(?<=\.)\s+", read(path).replace("\n", " "))

        def states_requirement(sentence):
            return "Fable or Astra" in sentence and "scientific" in sentence.lower()

        for path in ("scientific/SKILL.md", "shared/workflow.md", "README.md"):
            self.assertTrue(any(map(states_requirement, sentences(path))), path)
        # The sentences that grant any coordinator model carry the exception in place.
        for path, anchor in (("shared/workflow.md", "switch their main session"),
                             ("README.md", "any model in either CLI")):
            sentence = next(s for s in sentences(path) if anchor in s)
            self.assertTrue(states_requirement(sentence), f"{path}: {sentence}")

    def test_freshness_rule_is_stated_consistently(self):
        self.assertIn("> 300", read("scripts/choose-builder.py"))
        for doc in ("shared/workflow.md", "shared/usage-format.md"):
            self.assertIn("five minutes", read(doc), doc)


class SkillFileTests(unittest.TestCase):
    def frontmatter(self, skill):
        text = read(f"{skill}/SKILL.md")
        match = re.match(r"---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(match, skill)
        return dict(line.split(": ", 1) for line in match.group(1).splitlines()), text

    def test_frontmatter_names_match_folders(self):
        for skill in SKILLS:
            fields, _ = self.frontmatter(skill)
            self.assertEqual(fields.get("name"), skill)
            self.assertTrue(fields.get("description"), skill)

    def test_workflows_load_only_on_explicit_invocation(self):
        for profile in PROFILES:
            fields, _ = self.frontmatter(profile)
            self.assertIn(f"/{profile}", fields["description"])
            self.assertLessEqual(fields["description"].count(". "), 1, profile)   # two sentences

    def test_relative_links_resolve(self):
        for path in [f"{skill}/SKILL.md" for skill in SKILLS] + ["README.md"]:
            text = read(path)
            for target in re.findall(r"\]\(([^)#]+)\)", text):
                if "://" in target:
                    continue
                self.assertTrue((ROOT / path).parent.joinpath(target).is_file(), f"{path}: {target}")


if __name__ == "__main__":
    unittest.main()
