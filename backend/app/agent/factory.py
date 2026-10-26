"""Deep-agent factory. ONLY place that imports deepagents (contract)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langgraph.checkpoint.sqlite import SqliteSaver

from .llm import build_llm
from .prompts import ORCHESTRATOR_PROMPT, SUBAGENTS
from .tools import estimate_cost, list_docs


def build_agent(project_dir: Path, db_path: Path):
    """Create the orchestrator agent scoped to one project.

    - FilesystemBackend rooted at project_dir (agent can only touch this project).
    - SqliteSaver at db_path persists threads/checkpoints (memory/resume).
    - HITL: write_file/edit_file pause for human approval.
    """
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    backend = FilesystemBackend(root_dir=str(project_dir), virtual_mode=True)
    checkpointer = SqliteSaver.from_conn_string(str(db_path))
    model = build_llm()
    return create_deep_agent(
        model=model,
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=SUBAGENTS,
        tools=[list_docs, estimate_cost],
        backend=backend,
        checkpointer=checkpointer,
        interrupt_on={"write_file": True, "edit_file": True},
    ), checkpointer


@contextmanager
def scoped_env(project_dir: Path) -> Iterator[None]:
    """Expose project dir to tools for the duration of a run."""
    old = os.environ.get("IDEA2SPECS_PROJECT_DIR")
    os.environ["IDEA2SPECS_PROJECT_DIR"] = str(project_dir)
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("IDEA2SPECS_PROJECT_DIR", None)
        else:
            os.environ["IDEA2SPECS_PROJECT_DIR"] = old
