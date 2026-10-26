"""FastAPI app — routes only (contract). Agent logic lives in app/agent/."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langchain.messages import AIMessageChunk, ToolMessage
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from . import store
from .agent.factory import build_agent, scoped_env
from .schemas import (
    ChatRequest,
    DocContent,
    DocMeta,
    ProjectCreate,
    ProjectSummary,
)

VERSION = "0.2.0"
PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"

app = FastAPI(title="idea2specsdocs", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ helpers
def _require_project(project_id: str):
    project = store.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Unknown project")
    return project


def _project_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "docs").mkdir(parents=True, exist_ok=True)
    return d


def _sse(data: dict) -> str:
    return json.dumps(data)


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION}


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectCreate) -> dict:
    project = store.create_project(body.title)
    _project_dir(project.project_id)
    return {
        "project_id": project.project_id,
        "thread_id": project.thread_id,
        "title": project.title,
    }


@app.get("/api/projects")
def get_projects() -> list[ProjectSummary]:
    return [
        ProjectSummary(project_id=p.project_id, title=p.title, updated_at=p.updated_at)
        for p in store.list_projects()
    ]


@app.get("/api/projects/{project_id}/docs")
def get_docs(project_id: str) -> dict:
    _require_project(project_id)
    metas: list[DocMeta] = store.list_docs(project_id)
    return {"docs": [m.model_dump(mode="json") for m in metas]}


@app.get("/api/projects/{project_id}/docs/{slug}")
def get_doc(project_id: str, slug: str) -> DocContent:
    _require_project(project_id)
    doc = store.read_doc(project_id, slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not ready yet")
    return doc


@app.post("/api/chat")
async def chat(body: ChatRequest):
    project = _require_project(body.project_id)
    pdir = _project_dir(body.project_id)
    db_path = store.checkpoint_path(body.project_id)
    config = {"configurable": {"thread_id": project.thread_id}}

    async def gen():
        with scoped_env(pdir):
            agent, checkpointer = build_agent(pdir, db_path)
            try:
                if body.resume is not None:
                    stream_input: object = Command(
                        resume={
                            "decisions": [d.model_dump() for d in body.resume],
                        }
                    )
                else:
                    if not body.message.strip():
                        yield _sse({"type": "error", "detail": "Empty message"})
                        return
                    stream_input = {
                        "messages": [{"role": "user", "content": body.message}]
                    }
                async for ns, mode, data in agent.astream(
                    stream_input,
                    config=config,
                    stream_mode=["messages", "updates", "custom"],
                    subgraphs=True,
                ):
                    is_sub = any(str(s).startswith("tools:") for s in (ns or ()))
                    source = (
                        next(
                            (str(s) for s in (ns or ()) if str(s).startswith("tools:")),
                            "main",
                        )
                        if is_sub
                        else "main"
                    )

                    if mode == "messages":
                        token, _meta = data
                        if isinstance(token, AIMessageChunk) and token.content:
                            if token.tool_call_chunks:
                                for tc in token.tool_call_chunks:
                                    if tc.get("name"):
                                        yield _sse(
                                            {
                                                "type": "tool_call",
                                                "source": source,
                                                "name": tc["name"],
                                                "args_preview": str(tc.get("args", ""))[
                                                    :200
                                                ],
                                            }
                                        )
                            else:
                                yield _sse(
                                    {
                                        "type": "token",
                                        "source": source,
                                        "text": str(token.content),
                                    }
                                )
                        elif isinstance(token, ToolMessage):
                            yield _sse(
                                {
                                    "type": "tool_call",
                                    "source": source,
                                    "name": token.name,
                                    "args_preview": str(token.content)[:200],
                                }
                            )
                    elif mode == "updates":
                        if isinstance(data, dict) and "__interrupt__" in data:
                            intr = data["__interrupt__"][0]
                            val = intr.value if hasattr(intr, "value") else intr
                            yield _sse(
                                {
                                    "type": "interrupt",
                                    "interrupt_id": str(getattr(intr, "id", "")),
                                    "action_requests": val.get("action_requests", []),
                                    "review_configs": val.get("review_configs", []),
                                }
                            )
                        elif isinstance(data, dict):
                            for node in data:
                                if node == "tools":
                                    yield _sse(
                                        {
                                            "type": "subagent",
                                            "status": "complete",
                                            "name": source,
                                        }
                                    )
                    elif mode == "custom":
                        yield _sse({"type": "custom", "source": source, "data": data})
                store.touch_project(body.project_id)
                yield _sse({"type": "done", "thread_id": project.thread_id})
            finally:
                checkpointer.conn.close()

    return EventSourceResponse(gen(), media_type="text/event-stream")


@app.get("/api/projects/{project_id}/docs/{slug}/download")
def download_doc(project_id: str, slug: str) -> PlainTextResponse:
    _require_project(project_id)
    doc = store.read_doc(project_id, slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not ready yet")
    return PlainTextResponse(
        doc.markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
    )
