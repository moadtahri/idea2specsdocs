"""Typed contracts for discovery, decisions, review findings and verification evidence."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DocSlug = Literal[
    "prd",
    "technical-spike",
    "sad-architecture",
    "api-specification",
    "database-schema",
    "security-blueprint",
    "devops-iac-spec",
    "qa-test-plan",
    "runbook",
]
Phase = Literal["specification", "implementation", "production", "future"]
ItemKind = Literal[
    "product_decision", "engineering_requirement", "deployment_input", "verification"
]
SKILL_IDS = (
    "product-completeness",
    "contract-consistency",
    "security-to-tests",
    "deployment-readiness",
)
BRIEF_FIELDS = (
    "vertical",
    "service",
    "purpose",
    "users",
    "workflows",
    "scope",
    "permissions",
    "data_lifecycle",
    "constraints",
    "success_criteria",
)


def now() -> str:
    return datetime.now(UTC).isoformat()


class ProjectBrief(BaseModel):
    vertical: str = Field(default="", max_length=2000)
    service: str = Field(default="", max_length=2000)
    purpose: str = Field(default="", max_length=3000)
    users: str = Field(default="", max_length=3000)
    workflows: str = Field(default="", max_length=5000)
    scope: str = Field(default="", max_length=5000)
    permissions: str = Field(default="", max_length=4000)
    data_lifecycle: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)
    success_criteria: str = Field(default="", max_length=4000)
    # What the user brought: a new idea, a codebase plus a feature, or a codebase to clean up.
    # It selects the mode file wizi works with (agent/stages.py); never counted as missing.
    intake: Literal["idea", "feature", "cleanup"] = "idea"
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    sources: list[str] = Field(default_factory=list, max_length=40)
    open_questions: list[str] = Field(default_factory=list, max_length=15)


class WorkItemInput(BaseModel):
    kind: ItemKind
    title: str = Field(min_length=3, max_length=200)
    detail: str = Field(min_length=3, max_length=5000)
    impact: Phase = "implementation"
    owner: str = Field(default="Unassigned", max_length=200)
    affected_docs: list[DocSlug] = Field(min_length=1, max_length=9)
    proposal: str = Field(default="", max_length=5000)
    requirement_ids: list[str] = Field(default_factory=list, max_length=100)
    source: str = Field(default="", max_length=2000)
    # Who settles it: the stakeholder answers, wizi proposes an engineering default for the
    # user to confirm, or the code shows it (looked up, never voted on).
    owner_type: Literal["stakeholder", "default", "repo"] = "stakeholder"
    # Items that must be resolved first. Each must already exist, so the graph has no cycles.
    blocked_by: list[str] = Field(default_factory=list, max_length=20)


class WorkItem(WorkItemInput):
    id: str
    status: Literal["open", "proposed", "resolved", "deferred"] = "open"
    resolution: str = ""
    basis: Literal["proposal", "user_confirmed", "user_answered"] = "proposal"
    # The user's own words that settled it in chat (basis "user_answered").
    answered_with: str = ""
    updated_at: str = Field(default_factory=now)


class ItemResolution(BaseModel):
    status: Literal["resolved", "deferred", "open"]
    resolution: str = Field(default="", max_length=5000)


class Citation(BaseModel):
    slug: DocSlug
    line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=600)


class Finding(BaseModel):
    id: str = ""
    category: Literal[
        "product-completeness",
        "contract-consistency",
        "security-to-tests",
        "deployment-readiness",
        "evidence",
    ]
    severity: Literal["blocker", "warning", "info"]
    impact: Phase
    title: str = Field(min_length=3, max_length=200)
    detail: str = Field(min_length=3, max_length=4000)
    recommendation: str = Field(min_length=3, max_length=3000)
    affected_docs: list[DocSlug] = Field(min_length=1, max_length=9)
    citations: list[Citation] = Field(default_factory=list, max_length=10)


class ReviewDraft(BaseModel):
    summary: str = Field(min_length=3, max_length=5000)
    checks_completed: list[
        Literal[
            "product-completeness",
            "contract-consistency",
            "security-to-tests",
            "deployment-readiness",
        ]
    ]
    findings: list[Finding] = Field(default_factory=list, max_length=60)


class EvidenceInput(BaseModel):
    scope: Literal["implementation", "production"]
    environment: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(min_length=1, max_length=200)
    outcome: Literal["passed", "failed"]
    command: str = Field(min_length=1, max_length=2000)
    summary: str = Field(min_length=3, max_length=3000)
    attachment_id: str
    covered_ids: list[str] = Field(min_length=1, max_length=200)
    attested: Literal[True]

    @field_validator("source_revision")
    @classmethod
    def known_revision(cls, value: str) -> str:
        if value.strip().casefold() in ("", "unknown", "tbd", "n/a"):
            raise ValueError("Provide the code revision that was actually checked")
        return value.strip()


class Evidence(EvidenceInput):
    id: str
    spec_revision: str
    artifact_sha256: str
    created_at: str = Field(default_factory=now)


class ReviewRequest(BaseModel):
    environment: str = Field(default="production", min_length=1, max_length=100)


class QuestionsReturn(BaseModel):
    """The text of a package's .ai/questions.md, brought back by the user (spec 06)."""

    markdown: str = Field(min_length=1, max_length=200_000)


class BriefApproval(BaseModel):
    revision: str
