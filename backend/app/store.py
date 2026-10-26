"""Project + docs store: SQLite registry (app.db) + plain Markdown files.

Checkpoints (conversation memory) live in per-project SQLite files managed by
langgraph-checkpoint-sqlite — see agent/factory.py. This module only handles the
project registry and the 9 handover doc files.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .schemas import DOC_SLUGS, DOC_TITLES, DocContent, DocMeta, Project

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
PROJECTS_DIR = BACKEND_DIR / "projects"
REGISTRY_DB = DATA_DIR / "app.db"


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
    return conn


def _docs_dir(project_id: str) -> Path:
    d = PROJECTS_DIR / project_id / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


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


# ------------------------------------------------------------------ docs
def list_docs(project_id: str) -> list[DocMeta]:
    d = _docs_dir(project_id)
    metas: list[DocMeta] = []
    for slug in DOC_SLUGS:
        f = d / f"{slug}.md"
        updated = (
            datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) if f.exists() else None
        )
        metas.append(DocMeta(slug=slug, title=DOC_TITLES[slug], updated_at=updated))
    return metas


def read_doc(project_id: str, slug: str) -> DocContent | None:
    if slug not in DOC_SLUGS:
        return None
    f = _docs_dir(project_id) / f"{slug}.md"
    if not f.exists():
        return None
    return DocContent(slug=slug, title=DOC_TITLES[slug], markdown=f.read_text())


def checkpoint_path(project_id: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{project_id}.db"
