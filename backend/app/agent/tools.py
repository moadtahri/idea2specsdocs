"""Custom agent tools. Pure functions — no FastAPI imports (contract)."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

# ToolRuntime at module level: postponed annotations are resolved against this module.
from langchain.tools import ToolRuntime, tool

PROJECT_DIRECTORY: ContextVar[Path | None] = ContextVar(
    "project_directory", default=None
)


def _docs_dir() -> Path:
    # Resolved per-call from env to keep tools side-effect free in signature.
    import os

    root = PROJECT_DIRECTORY.get() or os.environ.get("IDEA2SPECS_PROJECT_DIR", ".")
    d = Path(root) / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool
def list_docs() -> str:
    """List the 9 handover doc slugs and whether each exists yet."""
    from ..schemas import DOC_SLUGS

    d = _docs_dir()
    lines = [
        f"{slug}: {'draft available (not verified)' if (d / f'{slug}.md').exists() else 'missing'}"
        for slug in DOC_SLUGS
    ]
    return "\n".join(lines)


def _project_id() -> str:
    directory = PROJECT_DIRECTORY.get()
    if directory is None:
        raise ValueError("No project is selected")
    return directory.name


@tool
def get_project_context() -> dict:
    """Read the persistent brief and shared decision/requirements register.
    frontier lists the IDs of open items whose blockers are settled: ask these now."""
    from .. import quality_store as qs

    project = _project_id()
    work = qs.items(project)
    return {
        "brief": qs.brief_state(project),
        "items": [item.model_dump() for item in work],
        "frontier": qs.frontier(work),
    }


@tool
def propose_project_brief(brief: dict) -> dict:
    """Save a proposed brief for the user's Review project brief / Approve brief buttons.

    Fields: vertical, service, purpose, users, workflows, scope, permissions,
    data_lifecycle, constraints, success_criteria (strings), assumptions, sources,
    open_questions (string arrays), intake ("idea": nothing built yet, "feature": a
    codebase plus a request, "cleanup": a codebase to redo or clean up).
    Preserve unanswered fields as empty strings.
    Read supplied context first; never fabricate answers. This does not approve it.
    """
    from .. import quality_store as qs
    from ..quality_models import ProjectBrief

    return qs.propose_brief(_project_id(), ProjectBrief.model_validate(brief))


def _listed(value: list[str] | str | None) -> list[str]:
    """Models often send a list as its JSON text ('["prd"]'); accept both forms."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            import json

            try:
                return [str(v) for v in json.loads(text)]
            except ValueError:
                pass
        return [part.strip() for part in text.split(",") if part.strip()]
    return list(value)


@tool
def propose_work_item(
    kind: str,
    title: str,
    detail: str,
    affected_docs: list[str] | str,
    impact: str = "implementation",
    owner: str = "Unassigned",
    proposal: str = "",
    requirement_ids: list[str] | str | None = None,
    source: str = "",
    owner_type: str = "stakeholder",
    blocked_by: list[str] | str | None = None,
) -> dict:
    """Record a consequential unresolved decision, requirement, deployment input or verification.

    kind: product_decision, engineering_requirement, deployment_input or verification.
    affected_docs: canonical document slugs (prd, technical-spike, sad-architecture, api-specification,
    database-schema, security-blueprint, devops-iac-spec, qa-test-plan, runbook).
    impact: specification, implementation, production or future. proposal: your recommendation;
    proposals are never user-approved decisions.
    owner_type says who settles it: "stakeholder" (the user answers; default),
    "default" (an engineering default you propose for the user to confirm) or
    "repo" (a fact the code shows). blocked_by lists the IDs of existing items that
    must be resolved first; record blockers before the items they block.
    Record an item only once its question can be stated precisely.
    """
    # Flat arguments (spec 07's first live run): with one `item` dict the model passed the fields flat or dropped
    # required ones, and every save failed.
    from .. import quality_store as qs
    from ..quality_models import WorkItemInput

    value = WorkItemInput.model_validate(
        {
            "kind": kind,
            "title": title,
            "detail": detail,
            "affected_docs": _listed(affected_docs),
            "impact": impact,
            "owner": owner,
            "proposal": proposal,
            "requirement_ids": _listed(requirement_ids),
            "source": source,
            "owner_type": owner_type,
            "blocked_by": _listed(blocked_by),
        }
    )
    return qs.propose_item(_project_id(), value).model_dump()


def _latest_user_text(runtime: ToolRuntime | None) -> str:
    messages = (runtime.state or {}).get("messages", []) if runtime else []
    latest = next(
        (m for m in reversed(messages) if getattr(m, "type", "") == "human"), None
    )
    if latest is None:
        return ""
    content = latest.content
    if isinstance(content, str):
        return content
    return " ".join(part.get("text", "") for part in content if isinstance(part, dict))


@tool
def settle_decision(
    item_id: str,
    user_words: str,
    resolution: str = "",
    runtime: ToolRuntime = None,
) -> dict:
    """Record the user's answer to an open decision from their latest message.

    user_words: the exact words in the user's latest message that answer this item
    (a plain "yes" to your recommendations accepts each recommended item's proposal).
    resolution: the decision in full; leave empty to take the item's proposal.
    Settle only what the user answered. Repo-owned items are facts to look up, not
    decisions to settle.
    """
    from .. import quality_store as qs

    return qs.settle_item(
        _project_id(), item_id, user_words, resolution, _latest_user_text(runtime)
    ).model_dump()


@tool
def load_review_skill(name: str) -> str:
    """Read a review playbook: product-completeness, contract-consistency,
    security-to-tests or deployment-readiness."""
    from .quality_skills import load_skill

    return load_skill(name)


@tool
def check_bundle_contracts() -> dict:
    """Preflight current saved contracts, including explicit SEC-to-TC mappings.

    Run after saving QA and before claiming the bundle complete. This reads
    documents; it does not approve them or claim tests have executed.
    """
    from .. import quality

    project = _project_id()
    docs = quality.documents(project)
    return {
        "findings": quality.mechanical_findings(project),
        "security_coverage": quality.security_coverage(docs),
    }


@tool
def check_package() -> dict:
    """Check the agent package the user downloads: every spec task has Do, Files, Read, Verify, Blocked by and
    Status; every Read: link resolves to a packaged section; blockers exist; the skill stays small and decision-free.

    Run after the last spec is written and after changing a spec. Fix blockers through the normal approval cards.
    """
    from .. import package, package_checks

    return package_checks.summary(
        package_checks.findings(package.package_files(_project_id()))
    )


@tool
async def review_bundle(environment: str = "production") -> dict:
    """Independently review existing drafts with cited findings; does not execute code."""
    from .review import run_review

    return await run_review(_project_id(), environment)


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
