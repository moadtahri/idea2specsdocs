"""The project's spec files: the plan, the conventions and one spec per slice of work (spec 05).

They live in ``projects/<id>/specs/``. ``README.md`` is the plan: it links every spec by file name, in order.
``agents.md`` holds the project conventions that become ``AGENTS.md`` in the package. The specs stage lasts
until the plan, the conventions and every spec the plan links exist.
"""

from __future__ import annotations

import re
from pathlib import Path

PLAN = "README.md"
CONVENTIONS = "agents.md"
SPEC_FILE = re.compile(r"^\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
LINKED = re.compile(r"\b(\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*\.md)\b")


def specs_dir(project_dir: Path) -> Path:
    return project_dir / "specs"


def is_spec_name(name: str) -> bool:
    return name in (PLAN, CONVENTIONS) or bool(SPEC_FILE.match(name))


def planned(project_dir: Path) -> list[str]:
    """Spec file names the plan links, in order, without repeats."""
    plan = specs_dir(project_dir) / PLAN
    if not plan.is_file():
        return []
    return list(dict.fromkeys(LINKED.findall(plan.read_text(encoding="utf-8"))))


def missing(project_dir: Path) -> list[str]:
    """What the specs stage still has to write: the plan, the conventions, then each planned spec."""
    directory = specs_dir(project_dir)
    wanted = [PLAN, CONVENTIONS, *planned(project_dir)]
    return [name for name in wanted if not (directory / name).is_file()]


def spec_files(project_dir: Path) -> list[Path]:
    """Every spec file present, plan and conventions first, then the specs in name order."""
    directory = specs_dir(project_dir)
    if not directory.is_dir():
        return []
    present = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and is_spec_name(path.name)
    )
    head = [
        directory / name for name in (PLAN, CONVENTIONS) if (directory / name).is_file()
    ]
    return head + [path for path in present if path.name not in (PLAN, CONVENTIONS)]
