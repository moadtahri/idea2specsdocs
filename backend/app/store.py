"""Project + docs store: SQLite registry (app.db) + plain Markdown files.

Checkpoints (conversation memory) live in per-project SQLite files managed by
langgraph-checkpoint-sqlite — see agent/factory.py. This module only handles the
project registry and the 9 handover doc files.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from . import specs
from .schemas import DOC_SLUGS, DOC_TITLES, Attachment, DocContent, DocMeta, Project

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROJECTS_DIR = BACKEND_DIR / "projects"
REGISTRY_DB = DATA_DIR / "app.db"

# Two virtual docs assembled from the 9 handover docs:
# - agent bundle: the machine-oriented handover for implementing agents
# - readable bundle: a plain-language version for people (LLM-generated, cached)
AGENT_BUNDLE_SLUG = "bundle-agent"
AGENT_BUNDLE_TITLE = "Handover Bundle (for agents)"
HUMAN_BUNDLE_SLUG = "bundle"
HUMAN_BUNDLE_TITLE = "Handover Bundle (readable)"
BUNDLE_SLUGS = (HUMAN_BUNDLE_SLUG, AGENT_BUNDLE_SLUG)
# Spec files (specs.py) appear in the document list as spec-<file name without .md>.
SPEC_PREFIX = "spec-"

# When docs disagree, the earlier entry wins for its area (stated in the bundle).
_PRECEDENCE = (
    "security-blueprint: security, privacy and compliance constraints override every other doc",
    "api-specification and database-schema: authoritative for interfaces and data shapes",
    "sad-architecture: authoritative for component boundaries and technology choices",
    "prd: authoritative for scope, behaviour and acceptance criteria",
    "devops-iac-spec, qa-test-plan, runbook, technical-spike: authoritative within their own area",
)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS attachments (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            text_preview TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )"""
    )
    return conn


def _uploads_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_attachment(
    project_id: str, filename: str, content_type: str, size: int, text_preview: str
) -> Attachment:
    att = Attachment(
        filename=filename,
        content_type=content_type,
        size=size,
        text_preview=text_preview,
    )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO attachments (id, project_id, filename, content_type, size, text_preview, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                att.attachment_id,
                project_id,
                filename,
                content_type,
                size,
                text_preview,
                att.created_at.isoformat(),
            ),
        )
    return att


def get_attachments(project_id: str, attachment_ids: list[str]) -> list[Attachment]:
    if not attachment_ids:
        return []
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM attachments WHERE project_id = ? AND id IN ({','.join('?' * len(attachment_ids))})",
            (project_id, *attachment_ids),
        ).fetchall()
    return [
        Attachment(
            attachment_id=r["id"],
            filename=r["filename"],
            content_type=r["content_type"],
            size=r["size"],
            text_preview=r["text_preview"],
            created_at=datetime.fromisoformat(r["created_at"]),
        )
        for r in rows
    ]


def _docs_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _doc_files(project_id: str) -> list[tuple[str, Path]]:
    d = _docs_dir(project_id)
    return [(slug, d / f"{slug}.md") for slug in DOC_SLUGS]


def _mtime(f: Path) -> datetime | None:
    return datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) if f.exists() else None


def docs_fingerprint(project_id: str) -> str:
    """sha256 over the current doc contents; changes whenever any doc changes."""
    h = hashlib.sha256()
    project = get_project(project_id)
    h.update((project.title if project else "").encode())
    h.update(b"\0")
    for slug, f in _doc_files(project_id):
        h.update(slug.encode())
        h.update(b"\0")
        h.update(b"present\0" if f.exists() else b"missing\0")
        h.update(f.read_bytes() if f.exists() else b"")
        h.update(b"\0")
    return h.hexdigest()


def has_any_doc(project_id: str) -> bool:
    return any(f.exists() for _slug, f in _doc_files(project_id))


def agent_bundle_markdown(project_id: str) -> str:
    """Single-file handover for implementing agents: manifest + rules + all docs."""
    project = get_project(project_id)
    title = project.title if project else project_id
    files = _doc_files(project_id)

    manifest = [
        "---",
        "bundle: itos/handover",
        "schema_version: 2",
        f"project: {json.dumps(title)}",
        f"project_id: {project_id}",
        f"generated_at: {_utcnow_iso()}",
        f"content_sha256: {docs_fingerprint(project_id)}",
        "documents:",
    ]
    for slug, f in files:
        updated = _mtime(f)
        manifest += [
            f"  - slug: {slug}",
            f"    title: {json.dumps(DOC_TITLES[slug])}",
            f"    status: {'draft' if f.exists() else 'missing'}",
            f"    updated_at: {updated.isoformat() if updated else 'null'}",
        ]
    manifest.append("---")

    parts = [
        *manifest,
        "",
        f"# Agent Handover Bundle: {title}",
        "",
        "## Instructions for implementing agents",
        "",
        (
            "1. This bundle is the source of truth for the project. Implement what it "
            "specifies; do not add features, dependencies or services it does not call for."
        ),
        "2. Keywords MUST, MUST NOT, SHOULD and MAY follow RFC 2119. MUST items are binding.",
        (
            "3. Requirement IDs (FR-, NFR-, AC-, SEC-, API-, DB-, OPS-, TC-) are stable. "
            "Reference them in code comments, commit messages and tests for traceability."
        ),
        "4. Contract ownership below helps route changes. Surface contradictions for reconciliation before implementing affected behavior; do not silently choose one contract:",
        *[f"   - {p}" for p in _PRECEDENCE],
        (
            "5. Items under Assumptions or Open questions are unresolved. Do not invent answers; "
            "surface them to a human before building anything that depends on them."
        ),
        (
            "6. Documents with status `missing` in the manifest have not been written yet. "
            "Do not infer their contents."
        ),
        "7. Each document is delimited by `<!-- BEGIN DOC slug=... -->` / `<!-- END DOC slug=... -->` markers.",
        (
            "8. For an existing-project feature, compare supplied source at its recorded revision "
            "with these contracts. Source describes current behavior; approved requirements describe "
            "the intended change. Flag drift, preserve unrelated behavior, and implement only the "
            "affected scope. Do not invent a repository revision or claim tests have run."
        ),
        (
            "9. Before implementation, confirm dependencies, affected requirement IDs, ordered tasks, "
            "migration and rollback steps, and acceptance/regression checks. Escalate missing "
            "information that blocks these tasks. A ready document is not proof of completed code."
        ),
        "",
    ]
    from .quality import bundle_quality_markdown

    parts += [
        "Draft content remains a proposal. Follow the readiness state and unresolved decisions below before implementing dependent work.",
        "",
        bundle_quality_markdown(project_id),
        "",
    ]
    for slug, f in files:
        body = (
            (f.read_text(encoding="utf-8").strip() or "*Empty document.*")
            if f.exists()
            else "*Not generated yet.*"
        )
        parts += [
            f"<!-- BEGIN DOC slug={slug} -->",
            "",
            f"## {DOC_TITLES[slug]} (`{slug}`)",
            "",
            body,
            "",
            f"<!-- END DOC slug={slug} -->",
            "",
        ]
    return "\n".join(parts).rstrip() + "\n"


def _human_bundle_cache(project_id: str) -> Path:
    # Kept outside the project dir so the agent's filesystem tools never see it.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{project_id}.bundle-readable.md"


def bundle_fingerprint(project_id: str) -> str:
    from . import quality_store as qs
    from .quality import policy_revision

    return qs.digest(
        {
            "spec": qs.spec_revision(project_id),
            "evidence": qs.evidence_revision(project_id),
            "review": qs.latest_review(project_id),
            "policy": policy_revision(),
        }
    )


def read_human_bundle_cache(project_id: str, fingerprint: str) -> str | None:
    f = _human_bundle_cache(project_id)
    if not f.exists():
        return None
    header, _, body = f.read_text(encoding="utf-8").partition("\n")
    return body if header == f"<!-- source-sha256: {fingerprint} -->" else None


def write_human_bundle_cache(project_id: str, fingerprint: str, markdown: str) -> None:
    _human_bundle_cache(project_id).write_text(
        f"<!-- source-sha256: {fingerprint} -->\n{markdown}", encoding="utf-8"
    )


# ------------------------------------------------------------------ projects
def create_project(title: str) -> Project:
    project = Project(title=title)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, thread_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                project.project_id,
                project.title,
                project.thread_id,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
            ),
        )
    _docs_dir(project.project_id)
    return project


def get_project(project_id: str) -> Project | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if row is None:
        return None
    return Project(
        project_id=row["id"],
        title=row["title"],
        thread_id=row["thread_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def list_projects() -> list[Project]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [
        Project(
            project_id=r["id"],
            title=r["title"],
            thread_id=r["thread_id"],
            created_at=datetime.fromisoformat(r["created_at"]),
            updated_at=datetime.fromisoformat(r["updated_at"]),
        )
        for r in rows
    ]


def touch_project(project_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (_utcnow_iso(), project_id),
        )


def rename_project(project_id: str, title: str) -> Project | None:
    with _connect() as conn:
        conn.execute(
            "UPDATE projects SET title = ?, updated_at = ? WHERE id = ?",
            (title, _utcnow_iso(), project_id),
        )
    return get_project(project_id)


def delete_project(project_id: str) -> bool:
    """Remove one registered project's files and registry records."""
    if get_project(project_id) is None:
        return False
    directory = (PROJECTS_DIR / project_id).resolve()
    if directory.parent != PROJECTS_DIR.resolve():
        raise ValueError("Project directory is outside the workspace")
    paths = [
        DATA_DIR / f"{project_id}{suffix}"
        for suffix in (
            ".db",
            ".db-wal",
            ".db-shm",
            ".db-journal",
            ".bundle-readable.md",
        )
    ]
    if any(path.resolve().parent != DATA_DIR.resolve() for path in paths):
        raise ValueError("Project data is outside the workspace")
    for path in paths:
        path.unlink(missing_ok=True)
    if directory.exists():
        shutil.rmtree(directory)
    with _connect() as conn:
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='project_quality'"
        ).fetchone():
            conn.execute(
                "DELETE FROM project_quality WHERE project_id = ?", (project_id,)
            )
        conn.execute("DELETE FROM attachments WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return True


# ------------------------------------------------------------------ docs
def list_docs(project_id: str) -> list[DocMeta]:
    metas = [
        DocMeta(slug=slug, title=DOC_TITLES[slug], updated_at=_mtime(f))
        for slug, f in _doc_files(project_id)
    ]
    updated_times = [m.updated_at for m in metas if m.updated_at is not None]
    bundle_updated = max(updated_times) if updated_times else None
    for path in specs.spec_files(PROJECTS_DIR / project_id):
        metas.append(
            DocMeta(
                slug=SPEC_PREFIX + path.stem,
                title=_spec_title(path),
                updated_at=_mtime(path),
            )
        )
    metas.append(
        DocMeta(
            slug=HUMAN_BUNDLE_SLUG, title=HUMAN_BUNDLE_TITLE, updated_at=bundle_updated
        )
    )
    metas.append(
        DocMeta(
            slug=AGENT_BUNDLE_SLUG, title=AGENT_BUNDLE_TITLE, updated_at=bundle_updated
        )
    )
    return metas


def _spec_title(path: Path) -> str:
    if path.name == specs.PLAN:
        return "Spec plan"
    if path.name == specs.CONVENTIONS:
        return "Project conventions (AGENTS.md)"
    match = re.search(r"^#\s+(.+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    return f"Spec · {match.group(1).strip() if match else path.stem}"


def read_doc(project_id: str, slug: str) -> DocContent | None:
    """Read one handover doc, a spec file or the agent bundle (the readable bundle is async; see main)."""
    if slug.startswith(SPEC_PREFIX):
        name = slug.removeprefix(SPEC_PREFIX) + ".md"
        path = specs.specs_dir(PROJECTS_DIR / project_id) / name
        if not specs.is_spec_name(name) or not path.is_file():
            return None
        return DocContent(
            slug=slug,
            title=_spec_title(path),
            markdown=path.read_text(encoding="utf-8"),
        )
    if slug == AGENT_BUNDLE_SLUG:
        return DocContent(
            slug=slug,
            title=AGENT_BUNDLE_TITLE,
            markdown=agent_bundle_markdown(project_id),
        )
    if slug not in DOC_SLUGS:
        return None
    f = _docs_dir(project_id) / f"{slug}.md"
    if not f.exists():
        return None
    return DocContent(
        slug=slug, title=DOC_TITLES[slug], markdown=f.read_text(encoding="utf-8")
    )


def checkpoint_path(project_id: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{project_id}.db"
