"""Mermaid diagrams for the readable bundle (spec 05 T6), built from structured data, never by the model.

The build order comes from the specs and their cross-spec ``Blocked by:``; the decision graph from the register's
``blocked_by`` edges. Neither can invent a component or a dependency the project does not record. The app draws them
(``MermaidDiagram.tsx``), and so do GitHub, VS Code and Notion.
"""

from __future__ import annotations

from . import quality_store as qs
from . import specs, store
from .package_checks import BLOCKER, tasks


def label(text: str) -> str:
    """A Mermaid node label: quotes and brackets would end it early."""
    clean = (
        text.replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\n", " ")
        .strip()
    )
    return f'"{clean[:60]}"'


def build_order(project_id: str) -> str | None:
    directory = store.PROJECTS_DIR / project_id
    numbered = {}
    edges = set()
    for path in specs.spec_files(directory):
        if path.name in (specs.PLAN, specs.CONVENTIONS):
            continue
        number = (
            path.name[:2] if path.name[:2].isdigit() else path.stem
        )  # a ticket stands alone
        text = path.read_text(encoding="utf-8")
        heading = next(
            (line[2:].strip() for line in text.splitlines() if line.startswith("# ")),
            path.stem,
        )
        numbered[number] = heading
        for fields in tasks(text).values():
            for other, _task in BLOCKER.findall(fields.get("Blocked by", "")):
                if other and other != number:
                    edges.add((other, number))
    if not numbered:
        return None
    lines = ["flowchart LR"]
    lines += [
        f"  s{number.replace('-', '_')}[{label(title)}]"
        for number, title in sorted(numbered.items())
    ]
    lines += [f"  s{a} --> s{b}" for a, b in sorted(edges) if a in numbered]
    return "\n".join(lines)


def decision_graph(project_id: str) -> str | None:
    work = qs.items(project_id)
    linked = {item.id for item in work if item.blocked_by} | {
        b for item in work for b in item.blocked_by
    }
    shown = [item for item in work if item.id in linked]
    if not shown:
        return None
    ids = {item.id: f"d{n}" for n, item in enumerate(shown, start=1)}
    lines = ["flowchart TD"]
    for item in shown:
        lines.append(
            f"  {ids[item.id]}[{label(item.title)}]:::{'settled' if item.status == 'resolved' else 'open'}"
        )
    for item in shown:
        lines += [f"  {ids[b]} --> {ids[item.id]}" for b in item.blocked_by if b in ids]
    lines += [
        "  classDef settled fill:#e3f1ea,stroke:#1e8a6e,color:#1b2b2a",
        "  classDef open fill:#fff4e0,stroke:#e0962b,color:#1b2b2a",
    ]
    return "\n".join(lines)


def section(project_id: str) -> str:
    parts = []
    if order := build_order(project_id):
        parts += [
            "### Build order",
            "",
            "Each box is a spec; an arrow means the later spec waits on work in the earlier one.",
            "",
            f"```mermaid\n{order}\n```",
            "",
        ]
    if graph := decision_graph(project_id):
        parts += [
            "### Decisions that wait on others",
            "",
            "Green is settled, amber is still open. An arrow points from a decision to the ones that wait on it.",
            "",
            f"```mermaid\n{graph}\n```",
            "",
        ]
    return "\n## Diagrams\n\n" + "\n".join(parts) if parts else ""
