#!/usr/bin/env python3
"""Link this repository's skills for Claude Code and Codex, replacing its retired links."""

import argparse
import os
from pathlib import Path
import subprocess

CURRENT = ("sol-review", "astra-review", "fable-review")
RETIRED = ("codex-review", "codex-implement", "opus-codex", "fable-codex",
           "low", "high", "scientific", "hard")


def default_destinations():
    """Claude Code reads ~/.claude/skills/<name>/SKILL.md; Codex reads ~/.codex/skills."""
    home = Path.home()
    return [home / ".claude" / "skills", home / ".codex" / "skills"]


def is_link(path):
    if path.is_symlink():
        return True
    return os.name == "nt" and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def link_target(link):
    """Where the link points by its own text, even when that target no longer exists."""
    text = os.readlink(link)
    if os.name == "nt" and text.startswith("\\\\?\\"):
        text = text[4:]
    return Path(os.path.realpath(os.path.join(link.parent, text)))


def plan(repo, destination):
    """Validate one destination and return the link changes it needs, touching nothing."""
    # mkdir(parents=True) needs the first existing ancestor to be a directory.
    ancestor = destination
    while not os.path.lexists(ancestor):
        ancestor = ancestor.parent
    if not ancestor.is_dir():
        raise ValueError(f"Skills directory path is not a directory: {ancestor}")
    actions = []
    for name in (*RETIRED, *CURRENT):
        link = destination / name
        target = repo / name
        if not os.path.lexists(link):
            if name in CURRENT:
                actions.append(("add", link, target))
            continue
        # A retired link's target is gone after `git pull`; judge it by link text.
        if not is_link(link) or link_target(link) != target:
            raise ValueError(f"Refusing to replace unrelated skill: {link}")
        if name in RETIRED:
            actions.append(("remove", link, target))
    return actions


def apply(destination, actions):
    destination.mkdir(parents=True, exist_ok=True)
    # Add new links before removing old ones.
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
            raise ValueError(f"Installed skill is unreadable: {destination / name}")
    print(f"Verified {', '.join(CURRENT)} in {destination}")


def install(repo, destinations):
    repo = repo.resolve()
    for name in CURRENT:
        if not (repo / name / "SKILL.md").is_file():
            raise ValueError(f"Missing skill: {name}")
    destinations = dict.fromkeys(d.expanduser().absolute() for d in destinations)
    # Validate every destination first, so a failure in one changes nothing anywhere.
    plans = [(destination, plan(repo, destination)) for destination in destinations]
    for destination, actions in plans:
        apply(destination, actions)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-dir", type=Path, action="append", metavar="DIR",
                        help="install only into DIR (repeatable); default: "
                             "~/.claude/skills and ~/.codex/skills")
    args = parser.parse_args(argv)
    try:
        install(Path(__file__).resolve().parents[1],
                args.skills_dir or default_destinations())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Installation failed: {error}\n")


if __name__ == "__main__":
    main()
