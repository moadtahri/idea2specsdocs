"""FastAPI app — routes only (contract). Agent logic lives in app/agent/."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from langchain.messages import AIMessageChunk, ToolMessage
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse

from . import store
from .agent.factory import build_agent, scoped_env
from .schemas import (
    Attachment,
    ChatRequest,
    DocContent,
    DocMeta,
    ProjectCreate,
    ProjectSummary,
)

VERSION = "0.2.0"
PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"

# Upload guardrails (contract §6: C1/C2)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "audio/webm",
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/ogg",
}
TEXT_PREVIEW_CHARS = 6000

logger = logging.getLogger("idea2specs.chat")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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


def _extract_thinking(token: AIMessageChunk) -> str:
    """Pull reasoning text out of a message chunk (provider-dependent shapes)."""
    parts: list[str] = []
    blocks = getattr(token, "content_blocks", None)
    if isinstance(blocks, list):
        for b in blocks:
            if isinstance(b, dict) and b.get("type") in (
                "reasoning",
                "thinking",
                "redacted_thinking",
            ):
                text = b.get("text") or b.get("thinking") or b.get("reasoning") or ""
                if text:
                    parts.append(str(text))
    extra = getattr(token, "additional_kwargs", None)
    if isinstance(extra, dict):
        for key in ("reasoning_content", "thinking"):
            val = extra.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
    return "".join(parts)


def _extract_todos(payload: object) -> list | None:
    """Pull a todos snapshot out of an updates payload, if present."""
    if isinstance(payload, dict):
        todos = payload.get("todos")
        if isinstance(todos, list):
            return [
                {
                    "content": t.get("content", ""),
                    "status": t.get("status", "pending"),
                }
                for t in todos
                if isinstance(t, dict)
            ]
    return None


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


def _extract_text(filename: str, content_type: str, raw: bytes) -> str:
    """Best-effort text extraction: plain text + markdown + json + csv inline;
    pdf/docx via installed libs if present, else a stub note for the agent.
    """
    name = filename.lower()
    if content_type.startswith("text/") or content_type == "application/json":
        return raw.decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(__import__("io").BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:  # noqa: BLE001 — extraction best-effort, stub on failure
            return f"[binary pdf: {filename}, text extraction unavailable]"
    if name.endswith(".docx"):
        try:
            import docx

            doc = docx.Document(__import__("io").BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception:  # noqa: BLE001 — extraction best-effort, stub on failure
            return f"[binary docx: {filename}, text extraction unavailable]"
    if content_type.startswith("audio/") or name.endswith(
        (".webm", ".mp3", ".mp4", ".wav", ".ogg", ".m4a")
    ):
        return "[audio attachment — use /api/transcribe result text instead]"
    return f"[binary file: {filename} ({content_type}), no text extraction]"


@app.post("/api/projects/{project_id}/uploads", status_code=201)
async def upload_file(
    project_id: str,
    file: UploadFile = File(...),  # noqa: B008
) -> Attachment:
    _require_project(project_id)
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    ctype = (file.content_type or "").split(";")[
        0
    ].strip() or "application/octet-stream"
    if ctype not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported type: {ctype}")
    uploads = PROJECTS_DIR / project_id / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    text = _extract_text(safe_name, ctype, raw)[:TEXT_PREVIEW_CHARS]
    att = store.save_attachment(
        project_id,
        filename=safe_name,
        content_type=ctype,
        size=len(raw),
        text_preview=text,
    )
    (uploads / f"{att.attachment_id}_{safe_name}").write_bytes(raw)
    logger.info(
        "[%s] 📎 upload %s (%s, %d bytes)",
        project_id[:8],
        safe_name,
        ctype,
        len(raw),
    )
    return att


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    """Transcribe an audio blob. Whisper if configured, else 501 with guidance."""
    ctype = (file.content_type or "").split(";")[0].strip()
    if not ctype.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Expected an audio file")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 10 MB)")
    try:
        from openai import OpenAI

        client = OpenAI()  # OPENAI_API_KEY env; whisper-1
        import io

        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename or "audio.webm", io.BytesIO(raw)),
        )
        text = resp.text or ""
        logger.info("🎤 transcribed %d bytes → %d chars", len(raw), len(text))
        return {"text": text}
    except Exception as e:
        logger.warning("transcribe unavailable: %.150s", str(e))
        raise HTTPException(
            status_code=501,
            detail=(
                "Server transcription unavailable (needs OPENAI_API_KEY + openai pkg). "
                "The app falls back to on-device Web Speech API in the browser."
            ),
        ) from e


@app.post("/api/chat")
async def chat(body: ChatRequest):
    project = _require_project(body.project_id)
    pdir = _project_dir(body.project_id)
    db_path = store.checkpoint_path(body.project_id)
    config = {"configurable": {"thread_id": project.thread_id}}

    async def gen():
        try:
            with scoped_env(pdir):
                agent, checkpointer_cm = await build_agent(pdir, db_path)
                last_todos: list = []
                if body.resume is not None:
                    logger.info(
                        "[%s] resume with %d decision(s)",
                        body.project_id[:8],
                        len(body.resume),
                    )
                    stream_input: object = Command(
                        resume={
                            "decisions": [d.model_dump() for d in body.resume],
                        }
                    )
                else:
                    if not body.message.strip() and not body.attachment_ids:
                        yield _sse({"type": "error", "detail": "Empty message"})
                        return
                    attachments = store.get_attachments(
                        body.project_id, body.attachment_ids
                    )
                    user_text = body.message.strip()
                    if attachments:
                        ctx = "\n\n".join(
                            f"[attached file: {a.filename} ({a.content_type}, {a.size} bytes)]\n{a.text_preview}"
                            for a in attachments
                        )
                        user_text = (
                            f"{user_text}\n\n--- attached context ---\n{ctx}"
                            if user_text
                            else f"Please review these attachments:\n\n{ctx}"
                        )
                    logger.info(
                        "[%s] user: %s",
                        body.project_id[:8],
                        user_text[:200],
                    )
                    stream_input = {
                        "messages": [{"role": "user", "content": user_text}]
                    }
                async for ns, mode, data in agent.astream(
                    stream_input,
                    config=config,
                    stream_mode=["messages", "updates", "custom", "values"],
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
                        if isinstance(token, AIMessageChunk):
                            # Reasoning/thinking blocks (provider-dependent)
                            thinking = _extract_thinking(token)
                            if thinking:
                                logger.info("[%s] 💭 %s", source, thinking[:300])
                                yield _sse(
                                    {
                                        "type": "thought",
                                        "source": source,
                                        "text": thinking,
                                    }
                                )
                            if token.content:
                                if token.tool_call_chunks:
                                    for tc in token.tool_call_chunks:
                                        if tc.get("name"):
                                            logger.info(
                                                "[%s] ⚙ %s %s",
                                                source,
                                                tc["name"],
                                                str(tc.get("args", ""))[:150],
                                            )
                                            yield _sse(
                                                {
                                                    "type": "tool_call",
                                                    "source": source,
                                                    "name": tc["name"],
                                                    "args_preview": str(
                                                        tc.get("args", "")
                                                    )[:200],
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
                            logger.info(
                                "[%s] ✔ %s → %.150s",
                                source,
                                token.name,
                                str(token.content),
                            )
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
                            names = [
                                a.get("name")
                                for a in val.get("action_requests", [])
                                if isinstance(a, dict)
                            ]
                            logger.info(
                                "[%s] ⏸ interrupt: awaiting approval for %s",
                                body.project_id[:8],
                                names,
                            )
                            yield _sse(
                                {
                                    "type": "interrupt",
                                    "interrupt_id": str(getattr(intr, "id", "")),
                                    "action_requests": val.get("action_requests", []),
                                    "review_configs": val.get("review_configs", []),
                                }
                            )
                        elif isinstance(data, dict):
                            for node, payload in data.items():
                                # node-step event: which graph node just ran
                                logger.info(
                                    "[%s] ▸ step: %s",
                                    source,
                                    node,
                                )
                                yield _sse(
                                    {
                                        "type": "step",
                                        "source": source,
                                        "node": node,
                                    }
                                )
                                if node == "tools":
                                    yield _sse(
                                        {
                                            "type": "subagent",
                                            "status": "complete",
                                            "name": source,
                                        }
                                    )
                                # todo snapshot may ride along on any update
                                todos = _extract_todos(payload)
                                if todos is not None and todos != last_todos:
                                    last_todos = todos
                                    done = sum(
                                        1
                                        for t in todos
                                        if t.get("status") == "completed"
                                    )
                                    logger.info(
                                        "[%s] ☑ todos %d/%d",
                                        body.project_id[:8],
                                        done,
                                        len(todos),
                                    )
                                    yield _sse({"type": "todos", "todos": todos})
                    elif mode == "values":
                        if isinstance(data, dict):
                            todos = data.get("todos")
                            if isinstance(todos, list) and todos != last_todos:
                                last_todos = todos
                                yield _sse({"type": "todos", "todos": todos})
                    elif mode == "custom":
                        yield _sse({"type": "custom", "source": source, "data": data})
                store.touch_project(body.project_id)
                logger.info("[%s] done", body.project_id[:8])
                yield _sse({"type": "done", "thread_id": project.thread_id})
                await checkpointer_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.exception("[%s] setup or agent run failed", body.project_id[:8])
            try:
                await checkpointer_cm.__aexit__(None, None, None)
            except (NameError, RuntimeError):
                pass  # CM never entered — nothing to close
            yield _sse({"type": "error", "detail": f"Agent failed: {e}"})

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
