"""FastAPI app — routes only (contract). Agent logic lives in app/agent/."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4

from anyio import CancelScope
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from langchain.messages import AIMessageChunk, ToolMessage
from langgraph.types import Command
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from . import (
    diagrams,
    package,
    package_checks,
    quality,
    questionnaire,
    store,
    typed_approval,
)
from . import quality_store as qs
from .agent.bundles import message_text, summarize_bundle
from .agent.factory import build_agent, scoped_env
from .agent.harness import from_harness
from .agent.llm import ModelConfigurationError
from .agent.review import run_review
from .quality_models import (
    BriefApproval,
    EvidenceInput,
    ItemResolution,
    ProjectBrief,
    QuestionsReturn,
    ReviewRequest,
    WorkItemInput,
)
from .schemas import (
    Attachment,
    ChatRequest,
    DocContent,
    DocMeta,
    ProjectCreate,
    ProjectSummary,
)
from .secrets import resolve_assemblyai_api_key
from .source_context import (
    SOURCE_EXTENSIONS,
    source_archive_context,
    source_files,
    write_source_tree,
)
from .transcription import TranscriptionError, create_streaming_token, transcribe_audio

VERSION = "0.2.0"
PROJECTS_DIR = Path(__file__).resolve().parent.parent / "projects"
_active_chats: set[str] = set()
_bundle_reads: dict[str, int] = {}
_chat_tasks: dict[str, asyncio.Task] = {}
_bundle_tasks: dict[str, set[asyncio.Task]] = {}
_quality_tasks: dict[str, set[asyncio.Task]] = {}
_deleting_projects: set[str] = set()

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

logger = logging.getLogger("itos.chat")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="itos", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ helpers
def _require_project(project_id: str):
    if project_id in _deleting_projects:
        raise HTTPException(status_code=404, detail="Project is being deleted")
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


def _harness_texts(payload: object) -> list[str]:
    """Texts of messages the harness added for the user in an updates payload."""
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return []
    return [
        text
        for message in messages
        if from_harness(message) and (text := message_text(message.content))
    ]


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "chat_progress": True,
        "transcription_provider": "assemblyai",
    }


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
async def get_docs(project_id: str) -> dict:
    _require_project(project_id)
    metas: list[DocMeta] = store.list_docs(project_id)
    state = quality.assessment(project_id)
    affected = {
        slug
        for finding in state["findings"]
        if finding["severity"] == "blocker"
        for slug in finding["affected_docs"]
    }
    return {
        "docs": [
            {
                **m.model_dump(mode="json"),
                "status": "missing"
                if not m.updated_at
                else "needs_attention"
                if m.slug in affected
                else "reviewed"
                if state["review_current"] and state["review_status"] == "complete"
                else "draft",
            }
            for m in metas
        ]
    }


@app.patch("/api/projects/{project_id}")
async def rename_project(project_id: str, body: ProjectCreate) -> ProjectSummary:
    _require_project(project_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Project name cannot be empty")
    project = store.rename_project(project_id, title)
    return ProjectSummary(
        project_id=project.project_id,
        title=project.title,
        updated_at=project.updated_at,
    )


@app.get("/api/projects/{project_id}/quality")
def project_quality(project_id: str, environment: str = "production") -> dict:
    _require_project(project_id)
    return quality.assessment(project_id, environment)


@app.put("/api/projects/{project_id}/brief")
def propose_brief(project_id: str, body: ProjectBrief) -> dict:
    _require_project(project_id)
    return qs.propose_brief(project_id, body)


@app.post("/api/projects/{project_id}/brief/approve")
def approve_brief(project_id: str, body: BriefApproval) -> dict:
    _require_project(project_id)
    try:
        return qs.approve_brief(project_id, body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/work-items", status_code=201)
def propose_work_item(project_id: str, body: WorkItemInput) -> dict:
    _require_project(project_id)
    try:
        return qs.propose_item(project_id, body).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/projects/{project_id}/work-items/{item_id}")
def resolve_work_item(project_id: str, item_id: str, body: ItemResolution) -> dict:
    _require_project(project_id)
    try:
        return qs.resolve_item(project_id, item_id, body).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Decision not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/evidence", status_code=201)
def record_evidence(project_id: str, body: EvidenceInput) -> dict:
    _require_project(project_id)
    try:
        known = set().union(
            *(
                quality.definitions(text)
                for text in quality.documents(project_id).values()
            )
        )
        if not set(body.covered_ids) <= known:
            raise ValueError(
                "Coverage must reference IDs defined in the current documents"
            )
        return qs.add_evidence(project_id, body).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/reviews")
async def review_project(project_id: str, body: ReviewRequest) -> dict:
    _require_project(project_id)
    task = asyncio.current_task()
    if _quality_tasks.get(project_id):
        raise HTTPException(
            status_code=409, detail="A review is already running for this project"
        )
    _quality_tasks.setdefault(project_id, set()).add(task)
    try:
        return await run_review(project_id, body.environment)
    finally:
        _quality_tasks.get(project_id, set()).discard(task)
        if not _quality_tasks.get(project_id):
            _quality_tasks.pop(project_id, None)


@app.delete("/api/projects/{project_id}", status_code=204)
async def delete_project(project_id: str) -> Response:
    _require_project(project_id)
    _deleting_projects.add(project_id)
    try:
        tasks = set(_bundle_tasks.get(project_id, set())) | set(
            _quality_tasks.get(project_id, set())
        )
        if project_id in _chat_tasks:
            tasks.add(_chat_tasks[project_id])
        tasks.discard(asyncio.current_task())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        store.delete_project(project_id)
    except OSError as exc:
        logger.exception("Project cleanup failed for %s", project_id)
        raise HTTPException(
            status_code=500,
            detail="Some project files could not be removed. Close any files in use and retry deletion.",
        ) from exc
    finally:
        _deleting_projects.discard(project_id)
        _active_chats.discard(project_id)
        _chat_tasks.pop(project_id, None)
        _bundle_tasks.pop(project_id, None)
        _quality_tasks.pop(project_id, None)
        _bundle_reads.pop(project_id, None)
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/docs/{slug}")
async def get_doc(project_id: str, slug: str) -> DocContent:
    _require_project(project_id)
    if slug in store.BUNDLE_SLUGS and not store.has_any_doc(project_id):
        raise HTTPException(status_code=404, detail="No documents are ready yet")
    if slug == store.HUMAN_BUNDLE_SLUG:
        fingerprint = store.bundle_fingerprint(project_id)
        markdown = store.read_human_bundle_cache(project_id, fingerprint)
        if markdown is None:
            source = store.agent_bundle_markdown(project_id)
            try:
                _bundle_reads[project_id] = _bundle_reads.get(project_id, 0) + 1
                task = asyncio.current_task()
                _bundle_tasks.setdefault(project_id, set()).add(task)
                try:
                    markdown = (
                        quality.bundle_quality_markdown(project_id)
                        + "\n"
                        + await summarize_bundle(source)
                    )
                finally:
                    _bundle_tasks[project_id].discard(task)
                    if not _bundle_tasks[project_id]:
                        _bundle_tasks.pop(project_id, None)
                    remaining = _bundle_reads[project_id] - 1
                    if remaining:
                        _bundle_reads[project_id] = remaining
                    else:
                        _bundle_reads.pop(project_id, None)
            except Exception as exc:
                logger.warning(
                    "Readable bundle generation failed (%s)", type(exc).__name__
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "The readable overview could not be generated. Please try again. "
                        "Your documents and agent bundle are still available."
                    ),
                ) from exc
            if store.bundle_fingerprint(project_id) != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Documents changed. Please reload the overview.",
                )
            store.write_human_bundle_cache(project_id, fingerprint, markdown)
        # Diagrams come from the specs and the register, so they are added fresh rather than cached (spec 05 T6).
        return DocContent(
            slug=slug,
            title=store.HUMAN_BUNDLE_TITLE,
            markdown=markdown + diagrams.section(project_id),
        )
    doc = store.read_doc(project_id, slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not ready yet")
    return doc


def _extract_text(filename: str, content_type: str, raw: bytes) -> str:
    """Best-effort text extraction: plain text + markdown + json + csv inline;
    pdf/docx via installed libs if present, else a stub note for the agent.
    """
    name = filename.lower()
    if (
        Path(name).suffix in SOURCE_EXTENSIONS
        or content_type.startswith("text/")
        or content_type == "application/json"
    ):
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
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    _require_project(project_id)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    ctype = (file.content_type or "").split(";")[
        0
    ].strip() or "application/octet-stream"
    safe_name = Path((file.filename or "upload").replace("\\", "/")).name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="Please provide a filename.")
    suffix = Path(safe_name).suffix.lower()
    if ctype not in ALLOWED_CONTENT_TYPES and suffix not in SOURCE_EXTENSIONS | {
        ".zip"
    }:
        raise HTTPException(status_code=415, detail=f"Unsupported type: {ctype}")
    uploads = PROJECTS_DIR / project_id / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    try:
        source = source_files(raw) if suffix == ".zip" else None
        full_text = (
            source_archive_context(raw)
            if source
            else _extract_text(safe_name, ctype, raw)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    text = full_text[:TEXT_PREVIEW_CHARS]
    if len(full_text) > TEXT_PREVIEW_CHARS:
        text += "\n[Preview truncated. Read the saved context file for the remaining content.]"
    att = store.save_attachment(
        project_id,
        filename=safe_name,
        content_type=ctype,
        size=len(raw),
        text_preview=text,
    )
    (uploads / f"{att.attachment_id}{suffix}").write_bytes(raw)
    (uploads / f"{att.attachment_id}.context.txt").write_text(
        full_text, encoding="utf-8"
    )
    if source:
        # A browsable copy for the repo reader (spec 04); the preview tells wizi where it is.
        write_source_tree(uploads / att.attachment_id, source[0])
    logger.info(
        "[%s] 📎 upload %s (%s, %d bytes)",
        project_id[:8],
        safe_name,
        ctype,
        len(raw),
    )
    return att


@app.post("/api/transcribe/token")
async def streaming_token() -> Response:
    api_key = await run_in_threadpool(resolve_assemblyai_api_key)
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Live transcription cannot access its AssemblyAI key. You can still record a voice note.",
        )
    try:
        token = await create_streaming_token(api_key)
    except TranscriptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(
        content=json.dumps(token),
        media_type="application/json",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.post("/api/transcribe")
async def transcribe(
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    """Transcribe recorded audio using credentials from AWS Secrets Manager."""
    ctype = (file.content_type or "").split(";")[0].strip()
    if not ctype.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Expected an audio file")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (max 10 MB)")
    if not raw:
        raise HTTPException(
            status_code=400, detail="The recording is empty. Please record again."
        )
    api_key = await run_in_threadpool(resolve_assemblyai_api_key)
    if not api_key:
        logger.warning("Transcription credential unavailable from AWS Secrets Manager")
        raise HTTPException(
            status_code=503,
            detail=(
                "Voice transcription cannot access its AssemblyAI key in AWS Secrets Manager. "
                "Check the backend AWS access to ASSEMBLYAI_API_KEY, then retry."
            ),
        )
    try:
        text = await transcribe_audio(raw, api_key)
        logger.info("🎤 transcribed %d bytes → %d chars", len(raw), len(text))
        return {"text": text}
    except TranscriptionError as e:
        logger.warning("Transcription failed (%s)", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail=str(e),
        ) from e
    except Exception as exc:
        logger.exception("Unexpected transcription failure")
        raise HTTPException(
            status_code=502,
            detail="Transcription could not finish. Please retry your recording.",
        ) from exc


@app.post("/api/chat")
async def chat(body: ChatRequest):
    project = _require_project(body.project_id)
    if body.project_id in _active_chats:
        raise HTTPException(
            status_code=409,
            detail="wizi is already working on this project. Wait for the current request to finish, then resend.",
        )
    pdir = _project_dir(body.project_id)
    db_path = store.checkpoint_path(body.project_id)
    config = {"configurable": {"thread_id": project.thread_id}}
    request_id = uuid4().hex[:12]
    _active_chats.add(body.project_id)
    _chat_tasks[body.project_id] = asyncio.current_task()

    async def gen():
        checkpointer_cm = None
        try:
            yield _sse(
                {
                    "type": "status",
                    "text": "Connecting to wizi…",
                    "request_id": request_id,
                }
            )
            with scoped_env(pdir):
                agent, checkpointer_cm = await build_agent(pdir, db_path)
                yield _sse(
                    {
                        "type": "status",
                        "text": "Reading your message and attachments…"
                        if body.attachment_ids
                        else "Reviewing your conversation…",
                    }
                )
                last_todos: list = []
                waiting = (
                    0  # actions a paused graph waits on, read only for a typed message
                )
                if body.resume is not None:
                    logger.info(
                        "[%s] resume with %d decision(s)",
                        body.project_id[:8],
                        len(body.resume),
                    )
                    stream_input: object = Command(
                        resume={
                            "decisions": [
                                d.model_dump(exclude_none=True) for d in body.resume
                            ],
                        }
                    )
                else:
                    if not body.message.strip() and not body.attachment_ids:
                        yield _sse({"type": "error", "detail": "Empty message"})
                        return
                    waiting = typed_approval.pending_actions(
                        await agent.aget_state(config)
                    )
                if waiting and body.message.strip():
                    # A card waits and the user typed or said their answer (spec 03 T5): the app decides, not wizi.
                    decisions = typed_approval.card_decisions(waiting, body.message)
                    approved = decisions[0]["type"] == "approve"
                    logger.info(
                        "[%s] typed answer to a waiting card: %s",
                        body.project_id[:8],
                        decisions[0]["type"],
                    )
                    yield _sse(
                        {
                            "type": "status",
                            "text": "Saving: you approved the waiting draft"
                            if approved
                            else "Sending your changes for the waiting draft",
                        }
                    )
                    stream_input = Command(resume={"decisions": decisions})
                elif body.resume is None:
                    attachments = store.get_attachments(
                        body.project_id, body.attachment_ids
                    )
                    user_text = body.message.strip()
                    if attachments:
                        yield _sse(
                            {
                                "type": "status",
                                "text": f"Preparing {len(attachments)} attached file(s) for review…",
                            }
                        )
                        ctx = "\n\n".join(
                            f"[attached file: {a.filename} ({a.content_type}, {a.size} bytes)]\n"
                            # Source goes to repo-reader only: pointing wizi at the snapshot invited it to read it
                            # whole (spec 07, run 4).
                            + (
                                f"Source tree for repo-reader: /uploads/{a.attachment_id}/source/ "
                                f"(index: /uploads/{a.attachment_id}/source-index.md)\n"
                                if (
                                    pdir
                                    / "uploads"
                                    / a.attachment_id
                                    / "source-index.md"
                                ).is_file()
                                else f"Full saved context: /uploads/{a.attachment_id}.context.txt\n"
                            )
                            + a.text_preview
                            for a in attachments
                        )
                        user_text = (
                            f"{user_text}\n\n--- attached context ---\n{ctx}"
                            if user_text
                            else f"Please review these attachments:\n\n{ctx}"
                        )
                    brief_note = typed_approval.approve_brief_from(
                        body.project_id, body.message
                    )
                    if brief_note:
                        user_text = f"{user_text}\n\n[{brief_note}]"
                        yield _sse({"type": "status", "text": brief_note})
                    logger.info(
                        "[%s] user: %s",
                        body.project_id[:8],
                        user_text[:200],
                    )
                    stream_input = {
                        "messages": [
                            {
                                "role": "user",
                                "content": user_text,
                                "id": body.message_id or uuid4().hex,
                            }
                        ]
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
                            if not is_sub:
                                text = message_text(token.content)
                                if text:
                                    yield _sse(
                                        {
                                            "type": "token",
                                            "source": "main",
                                            "text": text,
                                        }
                                    )
                            for tc in token.tool_call_chunks:
                                if tc.get("name"):
                                    yield _sse(
                                        {
                                            "type": "tool_call",
                                            "source": source,
                                            "name": tc["name"],
                                            "args_preview": "",
                                        }
                                    )
                        elif isinstance(token, ToolMessage):
                            yield _sse(
                                {
                                    "type": "tool_call",
                                    "source": source,
                                    "name": token.name,
                                    "args_preview": "",
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
                                # The harness's own messages (a turn limit) are not model tokens.
                                if not is_sub:
                                    for text in _harness_texts(payload):
                                        yield _sse(
                                            {
                                                "type": "token",
                                                "source": "main",
                                                "text": text,
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
                store.touch_project(body.project_id)
                logger.info("[%s] done", body.project_id[:8])
                yield _sse({"type": "done", "thread_id": project.thread_id})
        except ModelConfigurationError as exc:
            logger.warning(
                "[%s] model configuration unavailable: %s",
                body.project_id[:8],
                exc,
            )
            yield _sse(
                {
                    "type": "error",
                    "detail": (
                        "wizi cannot access its model credential in AWS Secrets "
                        "Manager. Check the backend AWS identity and model secret "
                        "configuration, then retry."
                    ),
                }
            )
        except Exception as exc:
            logger.exception("[%s] request %s failed", body.project_id[:8], request_id)
            kind = type(exc).__name__
            status = getattr(exc, "status_code", None)
            if kind == "GraphRecursionError":
                detail = "wizi reached its work limit before finishing. Resend with a smaller task, or delete this message."
            elif status in (401, 403):
                detail = "The model service rejected wizi's credentials. Please check model access before resending."
            elif status == 429:
                detail = "The model service is busy or its quota was reached. Wait a moment, then resend."
            elif status == 400:
                detail = "The model service could not process this conversation. Try resending with a smaller request or fewer attachments."
            elif kind in ("APITimeoutError", "TimeoutError"):
                detail = "The model service took too long to respond. You can resend this message."
            elif kind in ("APIConnectionError", "ConnectError"):
                detail = "wizi lost its connection to the model service. You can resend this message."
            else:
                detail = "wizi stopped before finishing. You can resend this message or delete it."
            yield _sse(
                {
                    "type": "error",
                    "detail": detail,
                    "request_id": request_id,
                }
            )

        finally:
            try:
                if checkpointer_cm is not None:
                    with CancelScope(shield=True):
                        await checkpointer_cm.__aexit__(None, None, None)
            finally:
                _active_chats.discard(body.project_id)
                _chat_tasks.pop(body.project_id, None)

    return EventSourceResponse(
        gen(),
        media_type="text/event-stream",
        ping=5,
        ping_message_factory=lambda: ServerSentEvent(data=_sse({"type": "heartbeat"})),
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.get("/api/projects/{project_id}/package")
def download_package(project_id: str) -> Response:
    """The agent package (spec 05): skill, specs, handover documents, decisions; unzip at the repository root."""
    project = _require_project(project_id)
    if not store.has_any_doc(project_id):
        raise HTTPException(status_code=404, detail="No documents are ready yet")
    filename = f"{package.slug(project.title)}-agent-package.zip"
    return Response(
        content=package.package_zip(project_id),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/projects/{project_id}/questionnaire")
def download_questionnaire(project_id: str) -> PlainTextResponse:
    """The decisions that can be settled now, as a file for a stakeholder outside the chat (spec 03 T6)."""
    project = _require_project(project_id)
    return PlainTextResponse(
        questionnaire.questionnaire_markdown(project_id),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{package.slug(project.title)}-questions.md"'
        },
    )


@app.post("/api/projects/{project_id}/questionnaire/answers")
def questionnaire_answers(project_id: str, body: QuestionsReturn) -> dict:
    """A filled questionnaire: each written answer settles its decision in the stakeholder's words."""
    _require_project(project_id)
    return questionnaire.apply_answers(project_id, body.markdown)


@app.get("/api/projects/{project_id}/package/checks")
def package_findings(project_id: str) -> dict:
    """What a coding agent would trip over in the package (spec 06). Warnings only: the download stays open."""
    _require_project(project_id)
    return package_checks.summary(
        package_checks.findings(package.package_files(project_id))
    )


@app.post("/api/projects/{project_id}/questions", status_code=201)
def return_questions(project_id: str, body: QuestionsReturn) -> dict:
    """A package's questions.md back from the coding agent: each open question opens a stakeholder decision."""
    _require_project(project_id)
    return package_checks.import_questions(project_id, body.markdown)


@app.get("/api/projects/{project_id}/docs/{slug}/download")
async def download_doc(project_id: str, slug: str) -> PlainTextResponse:
    doc = await get_doc(project_id, slug)
    return PlainTextResponse(
        doc.markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
    )
