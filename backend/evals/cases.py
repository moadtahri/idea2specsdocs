"""The eval cases: how each trial drives the app, and the checks that grade it.

A case's ``run`` returns a plain, JSON-ready trial record; its ``checks`` are pure functions of that record, so the
graders are tested without a model (``tests/test_evals.py``). A check returns ``(passed, note)``; ``passed`` is
``None`` when the trial never reached what it grades.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from app import specs, store
from app.quality_models import BRIEF_FIELDS

from . import fixtures
from .client import approve, chat, main_calls, quality

Result = tuple[bool | None, str]
YES = "Yes, go with your recommendations."
SALON = (
    b"Vertical: independent hair salons. Service: customers book haircut appointments with stylists. One salon, one "
    b"local time zone. No payment collection or marketplace. Existing workflow is booking by phone. Owner controls "
    b"schedules. Need to clarify cancellation, double bookings, customer identity and retention. Goal: reduce phone "
    b"calls."
)
WRITES = {"write_file", "edit_file", "write_todos"}
# Libraries, formats and tools a spec might pick on its own. One counts only when neither the documents nor the
# register name it (a default recorded for the user to confirm is named).
CHOICES = (
    "sqlalchemy",
    "alembic",
    "yaml",
    "toml",
    "redis",
    "celery",
    "django",
    "flask",
    "sqlite",
    "prisma",
    "poetry",
    "requirements.txt",
    "pipenv",
    "ruff",
    "black",
    "mypy",
    "httpx",
    "psycopg",
    "asyncpg",
    "sendgrid",
    "mailgun",
    "react",
    "vue",
    "tailwind",
    "htmx",
    "github actions",
    "gitlab",
    "docker",
    "kubernetes",
    "terraform",
    "pytest",
    "playwright",
    "selenium",
    "uvicorn",
    "gunicorn",
    "nginx",
    "apscheduler",
    "arq",
    "rq",
)


@dataclass
class Case:
    name: str
    run: Callable[[httpx.Client, str], dict]
    checks: dict[str, Callable[[dict], Result]]


def _new_brief(client: httpx.Client, project: str, intake: str = "idea") -> None:
    brief = {f: fixtures.BRIEF[f] for f in BRIEF_FIELDS}
    state = client.put(
        f"/api/projects/{project}/brief", json={**brief, "intake": intake}
    ).json()
    client.post(
        f"/api/projects/{project}/brief/approve", json={"revision": state["revision"]}
    ).raise_for_status()


# ------------------------------------------------------------------ discovery (specs 02, 03)


def run_discovery(client: httpx.Client, project: str) -> dict:
    upload = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("salon.txt", SALON, "text/plain")},
    )
    upload.raise_for_status()
    first = chat(
        client,
        project,
        "Use the uploaded context to clarify my requirements before creating a bundle. Ask the next useful questions.",
        attachment_ids=(upload.json()["attachment_id"],),
    )
    after_first = quality(client, project)
    second = chat(client, project, YES)
    after_second = quality(client, project)
    return {
        "turns": [first.summary(), second.summary()],
        "calls": main_calls(project),
        "items_before": after_first["items"],
        "frontier_before": after_first["frontier"],
        "items_after": after_second["items"],
        "docs_written": store.has_any_doc(project),
    }


def at_most_three_questions(trial: dict) -> Result:
    text = trial["turns"][0]["text"]
    asked = text.count("?")
    return bool(text.strip()) and asked <= 3, f"{asked} question marks"


def no_writes_or_specialists(trial: dict) -> Result:
    bad = [
        call["name"]
        if call["name"] != "task"
        else f"task:{call['args'].get('subagent_type')}"
        for call in trial["calls"]
        if call["name"] in WRITES
        or (
            call["name"] == "task"
            and call["args"].get("subagent_type") != "repo-reader"
        )
    ]
    return not bad and not trial["docs_written"], ", ".join(bad) or "none"


def uses_supplied_context(trial: dict) -> Result:
    text = trial["turns"][0]["text"].casefold()
    return any(term in text for term in ("salon", "haircut", "stylist")), ""


def decisions_have_edges(trial: dict) -> Result:
    items = trial["items_before"]
    waiting = [item for item in items if item.get("blocked_by")]
    return len(items) >= 2 and bool(
        waiting
    ), f"{len(items)} items, {len(waiting)} waiting"


def yes_settles_only_the_frontier(trial: dict) -> Result:
    before = {item["id"]: item for item in trial["items_before"]}
    settled = [
        item
        for item in trial["items_after"]
        if item["status"] == "resolved"
        and before.get(item["id"], {}).get("status") != "resolved"
    ]
    if not trial["frontier_before"]:
        return None, "no frontier to answer"
    stray = [
        i["title"]
        for i in settled
        if i["id"] not in trial["frontier_before"] or not i.get("answered_with")
    ]
    return (
        bool(settled) and not stray,
        f"{len(settled)} settled; outside the frontier or without words: {stray}",
    )


DISCOVERY = Case(
    "discovery",
    run_discovery,
    {
        "at_most_three_questions": at_most_three_questions,
        "no_writes_or_specialists": no_writes_or_specialists,
        "uses_supplied_context": uses_supplied_context,
        "decisions_have_edges": decisions_have_edges,
        "yes_settles_only_the_frontier": yes_settles_only_the_frontier,
    },
)


# ------------------------------------------------------------------ specs (specs 05, 06)

MAX_STEPS = 14
MAX_ANSWERS = 2


def run_specs(client: httpx.Client, project: str) -> dict:
    _new_brief(client, project)
    docs = store.PROJECTS_DIR / project / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for slug, text in fixtures.DOCS.items():
        (docs / f"{slug}.md").write_text(text, encoding="utf-8")
    directory = store.PROJECTS_DIR / project
    turns = [chat(client, project, "All nine documents are approved. Write the specs.")]
    resumes = []  # per approval of a spec file with more still to write: did the next card follow unasked?
    answers = 0
    for _ in range(MAX_STEPS):
        last = turns[-1]
        if last.errors:
            break
        if last.interrupts:
            approving_spec = any(
                a["path"].startswith("/specs/") for a in last.interrupts
            )
            nxt = approve(client, project, last)
            turns.append(nxt)
            if approving_spec and specs.missing(directory):
                # Going on is right; so is stopping to ask a decision the next spec needs (frontier open).
                went_on = any(a["path"].startswith("/specs/") for a in nxt.interrupts)
                asked = not nxt.interrupts and bool(
                    quality(client, project)["frontier"]
                )
                resumes.append(went_on or asked)
            continue
        if specs.missing(directory) and answers < MAX_ANSWERS:
            answers += 1
            turns.append(chat(client, project, YES))
            continue
        break
    state = quality(client, project)
    checks = client.get(f"/api/projects/{project}/package/checks").json()
    return {
        "turns": [turn.summary() for turn in turns],
        "continued": resumes,
        "missing": specs.missing(directory),
        "spec_text": "\n".join(
            p.read_text(encoding="utf-8") for p in specs.spec_files(directory)
        ),
        "docs_text": "\n".join(fixtures.DOCS.values()),
        "register_text": "\n".join(
            " ".join(
                str(item.get(k, ""))
                for k in ("title", "detail", "proposal", "resolution")
            )
            for item in state["items"]
        ),
        "package_blockers": checks["blockers"],
        "package_findings": [f["message"] for f in checks["findings"]][:10],
    }


def continues_after_approval(trial: dict) -> Result:
    if not trial["continued"]:
        return None, "no approval with more specs to write"
    went_on = sum(trial["continued"])
    return went_on == len(
        trial["continued"]
    ), f"{went_on}/{len(trial['continued'])} approvals led to the next card"


# What a named choice needs to work belongs to that choice (run 6): FastAPI's test client needs httpx, and ruff reads
# its settings only from a TOML file, GitHub Actions and Compose read only YAML. Counted as named only when the choice that needs it is named.
NEEDED_BY = {
    "httpx": ("fastapi",),
    "toml": ("ruff",),
    "yaml": ("github actions", "compose"),
}


def unnamed_choices(trial: dict) -> list[str]:
    named = f"{trial['docs_text']}\n{trial['register_text']}".casefold()
    used = trial["spec_text"].casefold()
    return [
        term
        for term in CHOICES
        if re.search(rf"\b{re.escape(term)}\b", used)
        and term not in named
        and not any(owner in named for owner in NEEDED_BY.get(term, ()))
    ]


def where_used(trial: dict, term: str) -> str:
    """The first spec line naming the term, so a reader can judge wizi against the grader."""
    pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    line = next(
        (
            line.strip()
            for line in trial["spec_text"].splitlines()
            if pattern.search(line)
        ),
        "",
    )
    return f"{term} in: {line[:160]}"


def decides_nothing_new(trial: dict) -> Result:
    if not trial["spec_text"]:
        return None, "no spec written"
    offenders = unnamed_choices(trial)
    return not offenders, " | ".join(
        where_used(trial, term) for term in offenders
    ) or "none"


def package_has_no_blockers(trial: dict) -> Result:
    if not trial["spec_text"]:
        return None, "no spec written"
    return trial["package_blockers"] == 0, "; ".join(trial["package_findings"][:3])


def reaches_review(trial: dict) -> Result:
    return not trial["missing"], f"still missing: {trial['missing']}"


SPECS = Case(
    "specs",
    run_specs,
    {
        "continues_after_approval": continues_after_approval,
        "decides_nothing_new": decides_nothing_new,
        "package_has_no_blockers": package_has_no_blockers,
        "reaches_review": reaches_review,
    },
)


# ------------------------------------------------------------------ repo reader (spec 04)

# Facts only the uploaded code shows: a reply using one read it (the user is told behaviour, not file names).
CODE_FACTS = ("/bookings", "routes.py", "models.py", "sqlite", "flask", "blueprint")


def run_repo_reader(client: httpx.Client, project: str) -> dict:
    upload = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("salon.zip", fixtures.source_zip(), "application/zip")},
    )
    upload.raise_for_status()
    turn = chat(
        client,
        project,
        "Here is our salon booking app's code. We want to add SMS reminders the day before each booking. Look at "
        "the code first, then ask only what you need from us.",
        attachment_ids=(upload.json()["attachment_id"],),
    )
    return {
        "turns": [turn.summary()],
        "calls": main_calls(project),
        "brief": quality(client, project)["brief"],
    }


def delegates_to_reader(trial: dict) -> Result:
    readers = [
        c
        for c in trial["calls"]
        if c["name"] == "task" and c["args"].get("subagent_type") == "repo-reader"
    ]
    others = [
        c["args"].get("subagent_type")
        for c in trial["calls"]
        if c["name"] == "task" and c not in readers
    ]
    return bool(
        readers
    ), f"{len(readers)} repo-reader call(s); other specialists: {others or 'none'}"


def never_reads_the_source_itself(trial: dict) -> Result:
    def path(call: dict) -> str:
        return str(call["args"].get("file_path") or call["args"].get("path") or "")

    reads = [
        path(c)
        for c in trial["calls"]
        if c["name"] in ("read_file", "grep", "glob", "ls")
        and "/uploads/" in path(c)
        and (".context.txt" in path(c) or "/source" in path(c))
    ]
    return not reads, ", ".join(reads) or "none"


def uses_facts_from_the_code(trial: dict) -> Result:
    text = trial["turns"][0]["text"].casefold()
    found = [fact for fact in CODE_FACTS if fact in text]
    return bool(found), ", ".join(found) or "none"


def intake_is_feature(trial: dict) -> Result:
    brief = trial["brief"]
    if not brief.get("revision"):
        return None, "no brief proposed yet"
    intake = brief.get("brief", {}).get("intake")
    return intake == "feature", f"intake {intake}"


REPO_READER = Case(
    "repo-reader",
    run_repo_reader,
    {
        "delegates_to_reader": delegates_to_reader,
        "never_reads_the_source_itself": never_reads_the_source_itself,
        "uses_facts_from_the_code": uses_facts_from_the_code,
        "intake_is_feature": intake_is_feature,
    },
)

# ------------------------------------------------------------------ questions back (spec 06)

RETURN_PLAN = "# Spec plan\n\n1. [01-booking-core.md](01-booking-core.md): booking and cancellation\n"
RETURN_SPEC = """# 01 Booking core

## Why
Owners book and cancel online (FR-1, FR-2).

## Tasks

### T1: Book a slot
**Do:** `POST /api/bookings` (API-1).
**Files:** `app/routes/bookings.py`, `tests/test_bookings.py`
**Read:** `.ai/handover/api-specification.md#bookings`
**Verify:** `pytest -q tests/test_bookings.py`
**Blocked by:** none
**Status:** done, 2026-10-30

### T2: Cancel a booking
**Do:** `DELETE /api/bookings/{id}?token=` (API-2).
**Files:** `app/routes/bookings.py`, `tests/test_cancel.py`
**Read:** `.ai/handover/api-specification.md#bookings`
**Verify:** `pytest -q tests/test_cancel.py`
**Blocked by:** T1
**Status:** todo
"""
RETURN_QUESTIONS = """# Questions for the project owners

### Q1: How does a guest owner get the cancel token?

- **Spec and task:** 01 T2
- **Why it blocks:** the cancel route needs the token, but no document says how the owner receives it
- **What was found:** API-2 takes `?token=`; the PRD says guests book without accounts
- **Options seen:** a link in the confirmation email; a code shown once on the booking page
- **Status:** open
"""
ANSWER = "Put the cancel link in the confirmation email."


def run_questions_back(client: httpx.Client, project: str) -> dict:
    _new_brief(client, project)
    directory = store.PROJECTS_DIR / project
    (directory / "docs").mkdir(parents=True, exist_ok=True)
    for slug, text in fixtures.DOCS.items():
        (directory / "docs" / f"{slug}.md").write_text(text, encoding="utf-8")
    folder = specs.specs_dir(directory)
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("README.md", RETURN_PLAN),
        ("agents.md", "# Conventions\n"),
        ("01-booking-core.md", RETURN_SPEC),
    ):
        (folder / name).write_text(text, encoding="utf-8")
    imported = client.post(
        f"/api/projects/{project}/questions", json={"markdown": RETURN_QUESTIONS}
    ).json()
    asked = chat(
        client,
        project,
        "I brought back the coding agent's questions. What do you need from me?",
    )
    answered = chat(client, project, ANSWER)
    turns = [asked, answered]
    for _ in range(4):  # approve the spec and document updates wizi proposes
        if not turns[-1].interrupts:
            break
        turns.append(approve(client, project, turns[-1]))
    items = quality(client, project)["items"]
    package = client.get(f"/api/projects/{project}/package")
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        decisions = archive.read(".ai/decisions.md").decode("utf-8")
        spec = archive.read(".ai/specs/01-booking-core.md").decode("utf-8")
    return {
        "turns": [turn.summary() for turn in turns],
        "imported": [item["id"] for item in imported["created"]],
        "items": items,
        "decisions_md": decisions,
        "spec_after": spec,
    }


def _returned(trial: dict) -> dict | None:
    return next((i for i in trial["items"] if i["id"] in trial["imported"]), None)


def asks_the_returned_question(trial: dict) -> Result:
    text = trial["turns"][0]["text"].casefold()
    return "cancel" in text and ("token" in text or "link" in text), ""


def settles_it_from_the_answer(trial: dict) -> Result:
    item = _returned(trial)
    if item is None:
        return False, "the question was not imported"
    return item["status"] == "resolved" and bool(item.get("answered_with")), (
        f"{item['status']}; words: {item.get('answered_with', '')!r}"
    )


def updates_the_spec_on_a_card(trial: dict) -> Result:
    carded = [a["path"] for t in trial["turns"] for a in t["interrupts"]]
    changed = "email" in trial["spec_after"].casefold()
    return any(
        p.startswith("/specs/01-") for p in carded
    ) and changed, f"cards: {carded}"


def package_carries_the_answer(trial: dict) -> Result:
    return "confirmation email" in trial["decisions_md"].casefold(), ""


QUESTIONS_BACK = Case(
    "questions-back",
    run_questions_back,
    {
        "asks_the_returned_question": asks_the_returned_question,
        "settles_it_from_the_answer": settles_it_from_the_answer,
        "updates_the_spec_on_a_card": updates_the_spec_on_a_card,
        "package_carries_the_answer": package_carries_the_answer,
    },
)

CASES = {case.name: case for case in (DISCOVERY, SPECS, REPO_READER, QUESTIONS_BACK)}
