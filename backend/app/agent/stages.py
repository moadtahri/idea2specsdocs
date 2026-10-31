"""The project's stage, and the stage and mode files the app adds to wizi's system message.

After the Canyas director's stage pin (KH-16): an agent told to read a stage's file when it gets there sometimes
skips the read, and with it the stage's rules. So the app works out the stage from the project's state and adds
the file itself. Canyas pins the file as a conversation message; here it goes into the system message instead.
Stages change about three times per project, so the cache cost is negligible, and a system-message file can neither
be folded away by compaction nor be mistaken for the user's words.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import hook_config
from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from .. import quality_store as qs
from .. import specs
from ..schemas import DOC_SLUGS
from .quality_skills import load_core_file

Stage = Literal["discovery", "drafting", "specs", "review"]
MODES_WITH_FILES = ("feature", "cleanup")


def current_stage(project_dir: Path) -> Stage:
    """Discovery until the brief is approved; drafting while any document is missing; specs while the plan, the
    conventions or a planned spec is missing; then review."""
    if qs.brief_state(project_dir.name)["status"] != "approved":
        return "discovery"
    docs = project_dir / "docs"
    if not all((docs / f"{slug}.md").is_file() for slug in DOC_SLUGS):
        return "drafting"
    if specs.missing(project_dir):
        return "specs"
    return "review"


def intake(project_dir: Path) -> str:
    return str(qs.brief_state(project_dir.name)["brief"].get("intake") or "idea")


def stage_files(stage: Stage, mode: str) -> list[str]:
    files = [f"stages/{stage}.md"]
    if mode in MODES_WITH_FILES:
        files.append(f"modes/{mode}.md")
    return files


def remaining_specs(project_dir: Path) -> str:
    """The specs stage's to-do, from disk: after an approved file wizi writes the next one without being asked, and a
    list it reads every call cannot drift from what is saved."""
    left = specs.missing(project_dir)
    return (
        "Still to write, in order: "
        + ", ".join(f"`/specs/{name}`" for name in left)
        + "."
    )


SAVED_PATH = re.compile(r"(/(?:docs|specs)/[\w.\-/]+?)[`'\".,]?(?:\s|$)")


NUDGE = "itos_continue"
MAX_NUDGES = 2


def nudged(message) -> bool:
    return bool((getattr(message, "additional_kwargs", None) or {}).get(NUDGE))


def just_saved(messages: list) -> str:
    """The document or spec saved most recently in this run, i.e. since the user's last message: the user approved it.

    The whole run counts, not only the last tool result: wizi often settles decisions or updates its to-do list in
    the same or the next step, and then the write is no longer the final message (spec 07, runs 6 and 7).
    """
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and not nudged(message):
            break
        if (
            isinstance(message, ToolMessage)
            and message.name in ("write_file", "edit_file")
            and message.status != "error"
            and (found := SAVED_PATH.search(str(message.content)))
        ):
            return found.group(1)
    return ""


def continue_after_save(project_dir: Path, messages: list) -> str:
    """When wizi ends its turn in the specs stage with specs still to write, no card waiting and no decision open for
    the user, the note that sends it back to write the next one; empty otherwise. A turn that ends on an open
    decision is a real stop. At most MAX_NUDGES since the latest save or user message, so it can never loop."""
    last = messages[-1] if messages else None
    if (
        not isinstance(last, AIMessage)
        or last.tool_calls
        or current_stage(project_dir) != "specs"
    ):
        return ""
    left = specs.missing(project_dir)
    if not left or qs.frontier(qs.items(project_dir.name)):
        return ""
    sent = 0
    for message in reversed(messages):
        if nudged(message):
            sent += 1
        elif isinstance(message, HumanMessage) or (
            isinstance(message, ToolMessage)
            and message.name in ("write_file", "edit_file")
            and message.status != "error"
        ):
            break
    if sent >= MAX_NUDGES:
        return ""
    if sent:
        # Run 9: after the first note wizi wrote its one line on the next spec and ended without writing it.
        return f"[The app: describing `/specs/{left[0]}` is not writing it. Call write_file for `/specs/{left[0]}` now.]"
    saved = just_saved(messages[:-1])
    done = (
        f"`{saved}` is saved and no card is waiting. "
        if saved
        else "Nothing is waiting on the user. "
    )
    # Run 10: wizi also ended on "Writing the plan file now:" before any file existed.
    return f"[The app: {done}Continue now: write `/specs/{left[0]}`, after one line on what it covers.]"


def stage_text(project_dir: Path, messages: list | None = None) -> str:
    stage = current_stage(project_dir)
    texts = [load_core_file(name) for name in stage_files(stage, intake(project_dir))]
    if stage == "specs":
        texts.append(remaining_specs(project_dir))
    if saved := just_saved(messages or []):
        # Pinned when it applies (spec 07, run 4 and the UI pass): right after an approval wizi often ended the turn
        # asking the user to approve the card they had just approved.
        line = (
            f"The user approved `{saved}` and it is saved: no card is waiting for it."
        )
        left = specs.missing(project_dir) if stage == "specs" else []
        if left:
            line += (
                f" Write `/specs/{left[0]}` now, in this turn, after one line on what it covers. "
                "Do not ask whether to continue."
            )
        else:
            line += " Say it is saved; never ask the user to approve it again."
        texts.append(line)
    return "\n\n".join(texts)


def with_text(system: SystemMessage | None, text: str) -> SystemMessage:
    if system is None:
        return SystemMessage(content=text)
    if isinstance(system.content, str):
        return SystemMessage(content=f"{system.content}\n\n{text}")
    return SystemMessage(content=[*system.content, {"type": "text", "text": text}])


class StageMiddleware(AgentMiddleware):
    """Before each model call, the files for where the project is now. Read per call: a document saved mid-run can
    move drafting to review."""

    def __init__(self, project_dir: Path):
        super().__init__()
        self.project_dir = project_dir

    def _with_stage(self, request):
        return request.override(
            system_message=with_text(
                request.system_message,
                stage_text(self.project_dir, list(request.messages or [])),
            )
        )

    def wrap_model_call(self, request, handler):
        return handler(self._with_stage(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._with_stage(request))

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime):
        # Enforced, not only asked (spec 07, run 7): with the pinned line in view wizi still ended some turns asking
        # for an approval it already had, and the user had to type "continue".
        note = continue_after_save(self.project_dir, list(state.get("messages", [])))
        if not note:
            return None
        return {
            "messages": [HumanMessage(content=note, additional_kwargs={NUDGE: True})],
            "jump_to": "model",
        }

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state, runtime):
        return self.after_model(state, runtime)
