"""Packaged, versioned application skills; no runtime fetching or arbitrary paths."""

from pathlib import Path

from ..quality_models import SKILL_IDS

SKILLS_DIR = Path(__file__).parent / "skills"
CORE_DIR = SKILLS_DIR / "wizi-core"
# Wizi's core skill and the files the app adds for a stage or an intake mode (stages.py).
CORE_FILES = frozenset(
    {
        "SKILL.md",
        "stages/discovery.md",
        "stages/drafting.md",
        "stages/specs.md",
        "stages/review.md",
        "modes/feature.md",
        "modes/cleanup.md",
    }
)


def load_skill(name: str) -> str:
    if name not in SKILL_IDS:
        raise ValueError("Unknown review skill")
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip()
    return text


def load_core_file(name: str) -> str:
    if name not in CORE_FILES:
        raise ValueError("Unknown wizi-core file")
    return strip_frontmatter((CORE_DIR / name).read_text(encoding="utf-8"))
