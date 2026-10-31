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
from langchain.messages import SystemMessage, ToolMessage

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


def just_saved(messages: list) -> str:
    """The document or spec the last tool result saved: the run is resuming right after the user approved it."""
    last = messages[-1] if messages else None
    if (
        isinstance(last, ToolMessage)
        and last.name in ("write_file", "edit_file")
        and last.status != "error"
        and (found := SAVED_PATH.search(str(last.content)))
    ):
        return found.group(1)
    return ""


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
