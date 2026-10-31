"""The agent package: a zip that drops into the user's repository (spec 05).

Fixed templates (``package_templates/``) carry how to work; the specs, the conventions and the nine documents carry
what to build. Paths inside the zip are the paths specs cite (``.ai/handover/<slug>.md`` for ``Read:``).
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from . import quality_store as qs
from . import specs, store
from .schemas import DOC_SLUGS, DOC_TITLES

TEMPLATES = Path(__file__).parent / "package_templates"
FIXED = (
    "procedures/task.md",
    "procedures/check.md",
    "procedures/refine.md",
    "procedures/commit.md",
    "scripts/check_scope.py",
)


def slug(title: str) -> str:
    return (
        re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:40].strip("-")
        or "project"
    )


def skill_name(title: str) -> str:
    return f"build-{slug(title)}"


def _template(name: str, values: dict[str, str]) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _first_heading(text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _decisions(project_id: str) -> str:
    owners = {
        "stakeholder": "project owner",
        "default": "recommended default",
        "repo": "fact from the code",
    }
    work = qs.items(project_id)
    lines = [
        "# Decisions",
        "",
        "What the project owners decided, and what is still open. Specs cite these; never re-decide them.",
        "",
    ]
    if not work:
        lines.append("No decisions were recorded.")
    titles = {item.id: item.title for item in work}
    for item in work:
        decided = item.status == "resolved"
        lines += [
            f"## {item.title}",
            "",
            f"- **Status:** {item.status} ({owners.get(item.owner_type, item.owner_type)})",
            f"- **Question:** {item.detail}",
            f"- **Decision:** {item.resolution if decided else 'not decided: do not build what depends on it'}",
        ]
        if item.answered_with:
            lines.append(f'- **The owner\'s words:** "{item.answered_with}"')
        if item.blocked_by:
            lines.append(
                f"- **Decided after:** {', '.join(titles.get(b, b) for b in item.blocked_by)}"
            )
        lines += [f"- **Affects:** {', '.join(item.affected_docs)}", ""]
    return "\n".join(lines).rstrip() + "\n"


def package_files(project_id: str) -> dict[str, str]:
    """Every file of the package, path to text."""
    project = store.get_project(project_id)
    title = project.title if project else project_id
    project_dir = store.PROJECTS_DIR / project_id
    intake = qs.brief_state(project_id)["brief"].get("intake") or "idea"
    skill = skill_name(title)
    in_root = (
        intake == "idea"
    )  # an existing repository keeps its own AGENTS.md / CLAUDE.md
    conventions_path = "AGENTS.md" if in_root else ".ai/AGENTS.md"

    files: dict[str, str] = {}
    spec_rows = []
    for path in specs.spec_files(project_dir):
        text = path.read_text(encoding="utf-8")
        if path.name == specs.CONVENTIONS:
            files[conventions_path] = text
            continue
        files[f".ai/specs/{path.name}"] = text
        if path.name != specs.PLAN:
            spec_rows.append(
                f"| `.ai/specs/{path.name}` | {_first_heading(text, path.stem)} |"
            )
    doc_rows = []
    for doc_slug in DOC_SLUGS:
        doc = project_dir / "docs" / f"{doc_slug}.md"
        if doc.is_file():
            files[f".ai/handover/{doc_slug}.md"] = doc.read_text(encoding="utf-8")
            doc_rows.append(
                f"| `.ai/handover/{doc_slug}.md` | {DOC_TITLES[doc_slug]} |"
            )
        else:
            doc_rows.append(f"| (not written) | {DOC_TITLES[doc_slug]} |")

    values = {
        "skill": skill,
        "project": title,
        "conventions": conventions_path,
        "spec_table": "| File | Spec |\n|---|---|\n" + "\n".join(spec_rows)
        if spec_rows
        else "No specs yet.",
        "doc_table": "| File | Document |\n|---|---|\n" + "\n".join(doc_rows),
    }
    base = f".claude/skills/{skill}"
    files[f"{base}/SKILL.md"] = _template("SKILL.md", values)
    for name in FIXED:
        files[f"{base}/{name}"] = _template(name, values)
    files[".ai/decisions.md"] = _decisions(project_id)
    files[".ai/questions.md"] = _template("questions.md", values)
    if in_root:
        files["CLAUDE.md"] = (
            f"@AGENTS.md\n\nBuild with the `{skill}` skill: one task per session, starting from `.ai/specs/README.md`.\n"
        )
    files[".ai/README.md"] = _readme(title, skill, conventions_path, in_root)
    return files


def _readme(title: str, skill: str, conventions: str, in_root: bool) -> str:
    merge = (
        ""
        if in_root
        else (
            "\n## Your repository already has conventions\n\n"
            f"The project conventions are in `{conventions}`. Merge them into your `AGENTS.md` or `CLAUDE.md`, or add "
            f"the line `@{conventions}` to your `CLAUDE.md`, and mention the `{skill}` skill there.\n"
        )
    )
    return (
        f"# Agent package: {title}\n\n"
        "Made by itos. Unzip it at the root of the repository.\n\n"
        "## Start\n\n"
        f"1. Open `.ai/specs/README.md`: the specs in build order.\n"
        f"2. In a fresh coding-agent session: `/{skill} refine 00` (or the first spec), then `/{skill} task 00 T1`.\n"
        f"3. After each task: `/{skill} check 00 T1`, review the findings, then `/{skill} commit 00 T1`. Each spec "
        "gets its branch (`spec/00-<name>`) and each task one commit (`00-T1: <task title>`). Start a new session "
        "for the next task.\n"
        "4. When the agent stops with a question, it is in `.ai/questions.md`: bring that file back to itos.\n"
        + merge
    )


def package_zip(project_id: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, text in sorted(package_files(project_id).items()):
            archive.writestr(path, text)
    return buffer.getvalue()
