"""Deep-agent factory. ONLY place that imports deepagents (contract)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .llm import build_llm
from .prompts import ORCHESTRATOR_PROMPT, SUBAGENTS
from .tools import estimate_cost, list_docs


async def build_agent(project_dir: Path, db_path: Path):
    """Create the orchestrator agent scoped to one project.

    - FilesystemBackend rooted at project_dir (agent can only touch this project).
    - AsyncSqliteSaver at db_path persists threads/checkpoints (memory/resume).
      Async saver is REQUIRED: the route streams via `agent.astream`.
    - HITL: write_file/edit_file pause for human approval.
    - TodoListMiddleware: agent maintains a `todos` plan visible in UI.
    """
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    backend = FilesystemBackend(root_dir=str(project_dir), virtual_mode=True)
    checkpointer_cm = AsyncSqliteSaver.from_conn_string(str(db_path))
    checkpointer = await checkpointer_cm.__aenter__()
    model = build_llm()
    try:
        agent = create_deep_agent(
            model=model,
            system_prompt=ORCHESTRATOR_PROMPT,
            subagents=SUBAGENTS,
            tools=[list_docs, estimate_cost],
            backend=backend,
            checkpointer=checkpointer,
            middleware=[TodoListMiddleware()],
            interrupt_on={"write_file": True, "edit_file": True},
        )
    except Exception:
        await checkpointer_cm.__aexit__(None, None, None)
        raise
    return agent, checkpointer_cm


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
