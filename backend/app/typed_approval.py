"""Typed and spoken approvals (spec 03 T5, after Canyas KH-12).

People answer a waiting card the way they answer a person: "yes, save it", or what to change. The app, not the
model, turns those words into the card's decision, so wizi can never approve its own work. Only a plain approval
counts as one; anything else is a change request carrying the user's words. The brief is stricter: only words that
name the brief approve it, because a bare "yes" in discovery settles decisions instead.
"""

from __future__ import annotations

import re

from . import quality_store as qs

APPROVALS = {
    "approve",
    "approved",
    "approve it",
    "approve and save",
    "yes",
    "yes please",
    "yes save it",
    "yes approve",
    "yes approve it",
    "yes looks good",
    "ok",
    "okay",
    "ok save it",
    "save",
    "save it",
    "looks good",
    "looks good save it",
    "lgtm",
    "go ahead",
    "sounds good",
    "perfect",
    "good",
    "fine",
    "accept",
    "accepted",
}
POLITE = {"thanks", "thank", "you", "please"}
BRIEF_APPROVAL = re.compile(
    r"^(?:yes )?(?:i )?(?:approve|approved|accept)(?: the)?(?: project)? brief$|^(?:the )?brief (?:is )?approved$"
)


def normal(text: str) -> str:
    words = re.sub(r"[^\w\s]", " ", text.casefold()).split()
    while words and words[-1] in POLITE:
        words.pop()
    return " ".join(words)


def is_approval(text: str) -> bool:
    return normal(text) in APPROVALS


def is_brief_approval(text: str) -> bool:
    return bool(BRIEF_APPROVAL.match(normal(text)))


def card_decisions(action_count: int, text: str) -> list[dict]:
    """The decisions a message makes for a waiting card: Approve, or Request changes with the message."""
    if is_approval(text):
        return [{"type": "approve"} for _ in range(action_count)]
    return [{"type": "reject", "message": text.strip()} for _ in range(action_count)]


def pending_actions(snapshot) -> int:
    """How many actions the paused graph waits on; 0 when nothing waits."""
    for interrupt in getattr(snapshot, "interrupts", ()) or ():
        value = getattr(interrupt, "value", None)
        if isinstance(value, dict) and value.get("action_requests"):
            return len(value["action_requests"])
    return 0


def approve_brief_from(project_id: str, text: str) -> str | None:
    """Approve the proposed brief when the words name it. Returns a note for wizi, or None when not a brief approval."""
    if not is_brief_approval(text):
        return None
    state = qs.brief_state(project_id)
    if state["status"] == "approved":
        return "The brief was already approved."
    if not state["revision"]:
        return "There is no proposed brief to approve yet."
    try:
        qs.approve_brief(project_id, state["revision"])
    except ValueError as problem:
        return f"The app could not approve the brief: {problem}"
    return "The app approved the brief from these words."
