"""Project-scoped quality state stored outside the agent's writable filesystem."""

import hashlib
import json
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from . import store
from .quality_models import (
    BRIEF_FIELDS,
    Evidence,
    EvidenceInput,
    ItemResolution,
    ProjectBrief,
    WorkItem,
    WorkItemInput,
    now,
)


@contextmanager
def connection():
    conn = store._connect()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS project_quality (project_id TEXT NOT NULL, category TEXT NOT NULL, item_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id, category, item_id))"
        )
        with conn:
            yield conn
    finally:
        conn.close()


def put(project_id: str, category: str, item_id: str, payload: dict):
    if store.get_project(project_id) is None:
        raise ValueError("Unknown project")
    with connection() as conn:
        conn.execute(
            "INSERT INTO project_quality VALUES (?, ?, ?, ?) ON CONFLICT(project_id, category, item_id) DO UPDATE SET payload=excluded.payload",
            (project_id, category, item_id, json.dumps(payload)),
        )


def rows(project_id: str, category: str) -> list[dict]:
    with connection() as conn:
        return [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT payload FROM project_quality WHERE project_id=? AND category=? ORDER BY rowid",
                (project_id, category),
            )
        ]


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def brief_state(project_id: str) -> dict:
    saved = rows(project_id, "brief")
    if not saved:
        return {
            "status": "clarifying",
            "brief": ProjectBrief().model_dump(),
            "revision": "",
            "missing": list(BRIEF_FIELDS),
        }
    state = saved[0]
    state["missing"] = [
        field
        for field in BRIEF_FIELDS
        if str(state["brief"].get(field, "")).strip().casefold()
        in ("", "tbd", "unknown", "to be decided", "?")
    ]
    return state


def propose_brief(project_id: str, brief: ProjectBrief) -> dict:
    revision = digest(brief.model_dump())
    current = brief_state(project_id)
    if current["revision"] == revision:
        return current
    put(
        project_id,
        "brief",
        "brief",
        {
            "brief": brief.model_dump(),
            "status": "proposed",
            "revision": revision,
            "updated_at": now(),
        },
    )
    return brief_state(project_id)


def approve_brief(project_id: str, revision: str) -> dict:
    state = brief_state(project_id)
    if state["revision"] != revision:
        raise ValueError(
            "The brief changed. Review the latest version before approving."
        )
    if state["missing"] or state["brief"]["open_questions"]:
        raise ValueError(
            "Resolve the brief's missing fields and open questions before approving."
        )
    if any(
        item.impact == "specification" and item.status in ("open", "proposed")
        for item in items(project_id)
    ):
        raise ValueError(
            "Resolve or explicitly defer specification decisions before approving the brief."
        )
    state.update(status="approved", approved_at=now())
    put(project_id, "brief", "brief", state)
    return state


def items(project_id: str) -> list[WorkItem]:
    return [WorkItem.model_validate(row) for row in rows(project_id, "item")]


def propose_item(project_id: str, value: WorkItemInput) -> WorkItem:
    existing = items(project_id)
    for item in existing:
        if (
            item.kind == value.kind
            and item.title.strip().casefold() == value.title.strip().casefold()
        ):
            return item
    known = {item.id for item in existing}
    unknown = [blocker for blocker in value.blocked_by if blocker not in known]
    if unknown:
        raise ValueError(
            f"Unknown blocking item(s): {', '.join(unknown)}. Record a blocker before the items it blocks."
        )
    prefixes = {
        "product_decision": "DEC",
        "engineering_requirement": "REQ",
        "deployment_input": "DEP",
        "verification": "VER",
    }
    item = WorkItem(
        **value.model_dump(),
        id=f"{prefixes[value.kind]}-{uuid4().hex[:8]}",
        status="proposed" if value.proposal else "open",
    )
    put(project_id, "item", item.id, item.model_dump())
    return item


def _plain(text: str) -> str:
    return " ".join(text.casefold().split())


def settle_item(
    project_id: str,
    item_id: str,
    user_words: str,
    resolution: str,
    latest_user_message: str,
) -> WorkItem:
    """Settle an open decision from the user's own words in chat. The words must be in their latest message, so
    the agent can never answer its own question; a bare answer (a plain "yes") takes the item's proposal."""
    item = next((item for item in items(project_id) if item.id == item_id), None)
    if item is None:
        raise ValueError(
            f"No decision {item_id}; read get_project_context for current IDs"
        )
    if item.owner_type == "repo":
        raise ValueError(
            "A repo-owned item is a fact to look up in the code, not a decision to settle"
        )
    if item.status not in ("open", "proposed"):
        raise ValueError(f"{item.title} is already {item.status}")
    words = _plain(user_words)
    if not words or not re.search(
        rf"(?<!\w){re.escape(words)}(?!\w)", _plain(latest_user_message)
    ):
        raise ValueError(
            "Those words are not in the user's latest message. Settle only what the user answered, "
            "quoting their words; ask them otherwise."
        )
    decision = resolution.strip() or item.proposal.strip()
    if not decision:
        raise ValueError("State the decision: this item has no proposal to accept")
    item.status = "resolved"
    item.resolution = decision
    item.basis = "user_answered"
    item.answered_with = user_words.strip()
    item.updated_at = now()
    put(project_id, "item", item.id, item.model_dump())
    return item


AGREEMENT = {
    "yes",
    "agree",
    "agreed",
    "ok",
    "okay",
    "accept",
    "as recommended",
    "recommended",
    "go with it",
}


def answer_item(
    project_id: str, item_id: str, answer: str, answered_by: str = ""
) -> WorkItem:
    """Settle an open decision from a stakeholder's written answer in a questionnaire (spec 03 T6). Same guards as
    settle_item: never a repo fact, never an item already settled; a bare agreement takes the item's proposal."""
    item = next((item for item in items(project_id) if item.id == item_id), None)
    if item is None:
        raise ValueError(f"No decision {item_id} in this project")
    if item.owner_type == "repo":
        raise ValueError(f"{item.title} is a fact to look up in the code")
    if item.status not in ("open", "proposed"):
        raise ValueError(f"{item.title} is already {item.status}")
    words = answer.strip()
    agreed = _plain(words).rstrip(".!") in AGREEMENT
    decision = item.proposal.strip() if agreed else words
    if not decision:
        raise ValueError(
            f"{item.title}: the answer agrees, but there was no recommendation to agree with"
        )
    item.status = "resolved"
    item.resolution = decision + (
        f" (answered by {answered_by.strip()} in a questionnaire)"
        if answered_by.strip()
        else " (answered in a questionnaire)"
    )
    item.basis = "user_answered"
    item.answered_with = words[:2000]
    item.updated_at = now()
    put(project_id, "item", item.id, item.model_dump())
    return item


def frontier(work_items: list[WorkItem]) -> list[str]:
    """Open items whose blockers are all resolved: the decisions that can be settled now.
    A deferred blocker keeps its dependents waiting."""
    resolved = {item.id for item in work_items if item.status == "resolved"}
    return [
        item.id
        for item in work_items
        if item.status in ("open", "proposed") and set(item.blocked_by) <= resolved
    ]


def resolve_item(project_id: str, item_id: str, resolution: ItemResolution) -> WorkItem:
    item = next((item for item in items(project_id) if item.id == item_id), None)
    if item is None:
        raise KeyError(item_id)
    if resolution.status != "open" and not resolution.resolution.strip():
        raise ValueError("Record the decision or the reason for deferring it")
    item.status = resolution.status
    item.resolution = resolution.resolution.strip()
    item.basis = "user_confirmed" if resolution.status != "open" else "proposal"
    item.updated_at = now()
    put(project_id, "item", item.id, item.model_dump())
    return item


def spec_revision(project_id: str) -> str:
    return digest(
        {
            "docs": store.docs_fingerprint(project_id),
            "brief": brief_state(project_id),
            "items": [item.model_dump() for item in items(project_id)],
        }
    )


def artifact_path(project_id: str, attachment_id: str) -> Path:
    attached = store.get_attachments(project_id, [attachment_id])
    if not attached:
        raise ValueError("Upload a verification result file belonging to this project")
    attachment = attached[0]
    directory = store.PROJECTS_DIR / project_id / "uploads"
    path = directory / f"{attachment_id}{Path(attachment.filename).suffix.lower()}"
    if not path.exists():
        path = directory / f"{attachment_id}_{attachment.filename}"
    if path.resolve().parent != directory.resolve() or not path.is_file():
        raise ValueError("The evidence attachment is unavailable")
    return path


def add_evidence(project_id: str, value: EvidenceInput) -> Evidence:
    sha = hashlib.sha256(
        artifact_path(project_id, value.attachment_id).read_bytes()
    ).hexdigest()
    record = Evidence(
        **value.model_dump(),
        id=uuid4().hex,
        spec_revision=spec_revision(project_id),
        artifact_sha256=sha,
    )
    put(project_id, "evidence", record.id, record.model_dump())
    return record


def evidence(project_id: str) -> list[dict]:
    result = []
    for row in rows(project_id, "evidence"):
        try:
            valid = (
                hashlib.sha256(
                    artifact_path(project_id, row["attachment_id"]).read_bytes()
                ).hexdigest()
                == row["artifact_sha256"]
            )
        except (ValueError, OSError):
            valid = False
        result.append({**row, "artifact_valid": valid})
    return result


def evidence_revision(project_id: str) -> str:
    return digest(evidence(project_id))


def latest_review(project_id: str) -> dict | None:
    reports = rows(project_id, "review")
    return reports[-1] if reports else None
