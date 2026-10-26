"""Custom agent tools. Pure functions — no FastAPI imports (contract)."""

from __future__ import annotations

from pathlib import Path

from langchain.tools import tool


def _docs_dir() -> Path:
    # Resolved per-call from env to keep tools side-effect free in signature.
    import os

    root = os.environ.get("IDEA2SPECS_PROJECT_DIR", ".")
    d = Path(root) / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool
def list_docs() -> str:
    """List the 9 handover doc slugs and whether each exists yet."""
    from ..schemas import DOC_SLUGS

    d = _docs_dir()
    lines = [
        f"{slug}: {'done' if (d / f'{slug}.md').exists() else 'missing'}"
        for slug in DOC_SLUGS
    ]
    return "\n".join(lines)


@tool
def estimate_cost(users: str, traffic: str, stack: str) -> str:
    """Rough monthly infra cost range. Args: users, traffic, stack description.

    Returns a range with assumptions — never a single precise number.
    """
    return (
        "Rough estimate (assumptions: single region, managed services, no staff cost):\n"
        f"- Input: users={users}, traffic={traffic}, stack={stack}\n"
        "- MVP/small: $20–$150/mo (single VM/containers + managed SQLite/Postgres)\n"
        "- Growing: $150–$800/mo (separate DB, CDN, backups, monitoring)\n"
        "Refine after traffic numbers and SLA are confirmed."
    )
