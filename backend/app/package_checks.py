"""Mechanical checks on the agent package, and the coding agent's questions coming back (spec 06).

The checks read exactly the files the zip holds (``package.package_files``), so what they pass is what the user
unzips. They warn; they never block the download. ``questions.md`` comes back as text written by a coding agent:
it is parsed as data, and each open question only opens a decision for the owners.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import quality_store as qs
from . import specs, store
from .quality_models import WorkItem, WorkItemInput
from .schemas import DOC_SLUGS

TASK_FIELDS = ("Do", "Files", "Read", "Verify", "Blocked by", "Status")
SKILL_MAX_LINES = 200
# A spec is known by its number ("01"), a standalone ticket by its file name ("ticket-sms-reminders").
SPEC_PATH = re.compile(r"^\.ai/specs/(?:(\d{2})-[a-z0-9-]+|(ticket-[a-z0-9-]+))\.md$")
TASK_HEADING = re.compile(r"^###\s+(T\d+)\b.*$", re.MULTILINE)
FIELD = re.compile(r"^\*\*([A-Za-z ]+):\*\*", re.MULTILINE)
LINK = re.compile(r"`(\.ai/[^`#\s]+)(?:#([^`\s]+))?`")
BLOCKER = re.compile(r"\b(?:(\d{2})[- ])?(T\d+)\b")
REQUIREMENT_ID = re.compile(r"\b(?:FR|NFR|SEC|API|DB|TC)-\d+")
FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.MULTILINE | re.DOTALL)
# "01 T2", "01-T2" or "ticket-sms-reminders T1": the spec number or ticket name, then the task.
TASK_REF = re.compile(r"\b(?:(\d{2}|ticket-[a-z0-9]+(?:-[a-z0-9]+)*?)[- ])?(T\d+)\b")
QUESTION = re.compile(r"^###\s+(Q\d+):\s*(.+)$", re.MULTILINE)
TEMPLATE_SECTION = re.compile(
    r"^##\s+Template\b.*?(?=^##\s|\Z)", re.MULTILINE | re.DOTALL
)
BULLET = re.compile(r"^-\s+\*\*([^*]+?):\*\*\s*(.*)$", re.MULTILINE)


def anchor(heading: str) -> str:
    """The specs stage's anchor rule: lower case, punctuation dropped, spaces as hyphens."""
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading.strip().casefold()))


def anchors(markdown: str) -> set[str]:
    text = FENCE.sub("", markdown)
    return {anchor(h) for h in re.findall(r"^#{1,6}\s+(.+?)\s*#*$", text, re.MULTILINE)}


def tasks(spec: str) -> dict[str, dict[str, str]]:
    """Each ``### T<n>`` section's bold fields, by task id."""
    found: dict[str, dict[str, str]] = {}
    headings = list(TASK_HEADING.finditer(spec))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(spec)
        section = spec[heading.end() : end]
        section = (
            section[: m.start()]
            if (m := re.search(r"^##\s", section, re.MULTILINE))
            else section
        )
        marks = list(FIELD.finditer(section))
        fields = {}
        for i, mark in enumerate(marks):
            stop = marks[i + 1].start() if i + 1 < len(marks) else len(section)
            fields[mark.group(1).strip()] = section[mark.end() : stop].strip()
        found[heading.group(1)] = fields
    return found


def findings(files: dict[str, str]) -> list[dict]:
    """Every problem a coding agent would trip over, as ``{severity, file, message}``."""
    out: list[dict] = []

    def add(severity: str, file: str, message: str) -> None:
        out.append({"severity": severity, "file": file, "message": message})

    spec_tasks = {
        match.group(1) or match.group(2): (path, tasks(text))
        for path, text in sorted(files.items())
        if (match := SPEC_PATH.match(path))
    }
    if not spec_tasks:
        add(
            "warning",
            ".ai/specs/",
            "The package has no specs yet: the coding agent has no task to start from.",
        )
    plan = files.get(".ai/specs/README.md", "")
    for name in dict.fromkeys(specs.LINKED.findall(plan)):
        if f".ai/specs/{name}" not in files:
            add(
                "blocker",
                ".ai/specs/README.md",
                f"The plan lists {name}, which is not in the package.",
            )

    for number, (path, spec_task_map) in spec_tasks.items():
        if not spec_task_map:
            add("blocker", path, "The spec has no `### T<n>` tasks.")
        for where, fields in spec_task_map.items():
            missing = [name for name in TASK_FIELDS if name not in fields]
            if missing:
                add("blocker", path, f"{where} has no {', '.join(missing)}.")
            if "Verify" in fields and not fields["Verify"].strip():
                add(
                    "blocker",
                    path,
                    f"{where} has an empty Verify: it cannot be checked.",
                )
            for target, part in LINK.findall(fields.get("Read", "")):
                if target not in files:
                    add(
                        "blocker",
                        path,
                        f"{where} reads `{target}`, which is not in the package.",
                    )
                elif part and part.casefold() not in anchors(files[target]):
                    add(
                        "blocker",
                        path,
                        f"{where} reads `{target}#{part}`: no such heading in that document.",
                    )
            blocked = fields.get("Blocked by", "")
            if blocked.strip().casefold().rstrip(".") not in ("", "none"):
                for other_spec, other_task in BLOCKER.findall(blocked):
                    owner = other_spec or number
                    if (
                        owner not in spec_tasks
                        or other_task not in spec_tasks[owner][1]
                    ):
                        add(
                            "warning",
                            path,
                            f"{where} waits on {owner}-{other_task}, which does not exist.",
                        )

    skill_files = {
        path: text for path, text in files.items() if path.startswith(".claude/skills/")
    }
    for path, text in skill_files.items():
        if path.endswith("/SKILL.md") and len(text.splitlines()) > SKILL_MAX_LINES:
            add(
                "warning",
                path,
                f"SKILL.md has {len(text.splitlines())} lines; keep it under {SKILL_MAX_LINES}.",
            )
        if path.endswith(".md") and (
            ids := sorted(set(REQUIREMENT_ID.findall(FENCE.sub("", text))))
        ):
            add(
                "warning",
                path,
                f"The skill names requirements ({', '.join(ids[:5])}): decisions belong in the specs.",
            )
        if "/procedures/" in path and not re.search(
            r"^Done when\b", text, re.MULTILINE
        ):
            add(
                "warning",
                path,
                "The procedure has no 'Done when' line: the agent cannot tell when it is finished.",
            )
    for path, text in files.items():
        if "{{" in text and "}}" in text:
            add("blocker", path, "A template placeholder ({{…}}) was left unfilled.")
    return out


def summary(found: list[dict]) -> dict:
    return {
        "blockers": sum(1 for f in found if f["severity"] == "blocker"),
        "warnings": sum(1 for f in found if f["severity"] == "warning"),
        "findings": found,
    }


def parse_questions(markdown: str) -> list[dict]:
    """Open ``### Q<n>:`` blocks, outside the template section."""
    body = TEMPLATE_SECTION.sub("", markdown)
    heads = list(QUESTION.finditer(body))
    out = []
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(body)
        block = re.split(
            r"^#{1,3}\s", body[head.end() : end], maxsplit=1, flags=re.MULTILINE
        )[0]
        fields = {
            name.strip().casefold(): value.strip()
            for name, value in BULLET.findall(block)
        }
        question = head.group(2).strip()
        if "<" in question and ">" in question:  # an unfilled template
            continue
        if not fields.get("status", "open").casefold().startswith("open"):
            continue
        reference = TASK_REF.search(fields.get("spec and task", ""))
        out.append(
            {
                "id": head.group(1),
                "question": question,
                "spec": reference.group(1) if reference else "",
                "task": reference.group(2) if reference else "",
                "why": fields.get("why it blocks", ""),
                "found": fields.get("what was found", ""),
                "options": fields.get("options seen", ""),
            }
        )
    return out


def task_docs(project_dir: Path, spec_number: str, task_id: str) -> list[str]:
    """The documents a task's Read: cites, as slugs; empty when the task is not found."""
    for path in specs.spec_files(project_dir):
        if path.stem == spec_number or path.name.startswith(f"{spec_number}-"):
            fields = tasks(path.read_text(encoding="utf-8")).get(task_id, {})
            cited = re.findall(
                r"\.ai/handover/([a-z0-9-]+)\.md", fields.get("Read", "")
            )
            return [slug for slug in dict.fromkeys(cited) if slug in DOC_SLUGS]
    return []


def import_questions(project_id: str, markdown: str) -> dict:
    """Open one stakeholder decision per open question; an existing title is returned, not duplicated."""
    project_dir = store.PROJECTS_DIR / project_id
    known = {item.title.strip().casefold() for item in qs.items(project_id)}
    created: list[WorkItem] = []
    existing: list[WorkItem] = []
    for question in parse_questions(markdown):
        where = f"{question['spec']} {question['task']}".strip() or "no task named"
        docs = (
            task_docs(project_dir, question["spec"], question["task"])
            if question["spec"]
            else []
        )
        detail = "\n".join(
            line
            for line in (
                question["question"],
                f"Why it blocks: {question['why']}" if question["why"] else "",
                f"What the coding agent found: {question['found']}"
                if question["found"]
                else "",
                f"Options it saw: {question['options']}" if question["options"] else "",
            )
            if line
        )
        item = qs.propose_item(
            project_id,
            WorkItemInput(
                kind="product_decision",
                title=question["question"][:200],
                detail=detail[:5000],
                impact="implementation",
                owner="Project owner",
                affected_docs=docs or ["prd"],
                source=f"Coding agent question {question['id']} ({where}), from .ai/questions.md",
                owner_type="stakeholder",
            ),
        )
        (existing if item.title.strip().casefold() in known else created).append(item)
        known.add(item.title.strip().casefold())
    return {
        "created": [item.model_dump() for item in created],
        "existing": [item.model_dump() for item in existing],
    }
