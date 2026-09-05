#!/usr/bin/env python3
"""Link this repository's skills, replacing its retired links."""

import argparse
import os
from pathlib import Path
import subprocess

CURRENT = ("low", "high", "scientific", "sol-review")
RETIRED = ("codex-review", "codex-implement", "opus-codex", "fable-codex")


def is_link(path):
    if path.is_symlink():
        return True
    return os.name == "nt" and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def install(repo, destination):
    repo = repo.resolve()
    destination = destination.expanduser().absolute()
    actions = []
    for name in (*RETIRED, *CURRENT):
        link = destination / name
        target = repo / name
        if not os.path.lexists(link):
            if name in CURRENT:
                actions.append(("add", link, target))
            continue
        if not is_link(link) or link.resolve() != target:
            raise ValueError(f"Refusing to replace unrelated skill: {link}")
        if name in RETIRED:
            actions.append(("remove", link, target))
    for name in CURRENT:
        if not (repo / name / "SKILL.md").is_file():
            raise ValueError(f"Missing skill: {name}")
    destination.mkdir(parents=True, exist_ok=True)
    # Validate everything first, then add new links before removing old ones.
    for action, link, target in sorted(actions, key=lambda item: item[0]):
        if action == "add":
            if os.name == "nt":
                subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J",
                                str(link), str(target)], check=True)
            else:
                link.symlink_to(target, target_is_directory=True)
        elif link.is_symlink():
            link.unlink()
        else:
            os.rmdir(link)  # Remove the junction itself, never its target.
        print(f"{action}: {link}")
    for name in CURRENT:
        if not (destination / name / "SKILL.md").is_file():
            raise ValueError(f"Installed skill is unreadable: {name}")
    print(f"Verified {', '.join(CURRENT)} in {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-dir", type=Path,
                        default=Path.home() / ".claude" / "skills")
    args = parser.parse_args()
    try:
        install(Path(__file__).resolve().parents[1], args.skills_dir)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Installation failed: {error}\n")


if __name__ == "__main__":
    main()
