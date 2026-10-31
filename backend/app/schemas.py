"""Pydantic v2 schemas — mirrors frontend types in src/api.ts (contract)."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------- projects
class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Project(BaseModel):
    project_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class ProjectSummary(BaseModel):
    project_id: str
    title: str
    updated_at: datetime


# ---------------------------------------------------------------- chat
DecisionType = Literal["approve", "edit", "reject"]


class ResumeDecision(BaseModel):
    type: DecisionType
    message: str = ""
    edited_action: dict | None = None


class ChatRequest(BaseModel):
    project_id: str
    message_id: str | None = Field(default=None, min_length=1, max_length=100)
    message: str = Field(default="", max_length=8000)
    resume: list[ResumeDecision] | None = None
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)


class Attachment(BaseModel):
    attachment_id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    content_type: str = ""
    size: int = 0
    text_preview: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ActionRequest(BaseModel):
    name: str
    args: dict


class InterruptPayload(BaseModel):
    interrupt_id: str = ""
    action_requests: list[ActionRequest] = Field(default_factory=list)
    review_configs: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------- docs
DOC_SLUGS: list[str] = [
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

DOC_TITLES: dict[str, str] = {
    "prd": "PRD",
    "technical-spike": "Technical Spike",
    "sad-architecture": "SAD / Architecture",
    "api-specification": "API Specification",
    "database-schema": "Database Schema",
    "security-blueprint": "Security Blueprint",
    "devops-iac-spec": "DevOps IaC Spec",
    "qa-test-plan": "QA Test Plan",
    "runbook": "Runbook / On-Call Docs",
}


class DocMeta(BaseModel):
    slug: str
    title: str
    updated_at: datetime | None = None


class DocContent(BaseModel):
    slug: str
    title: str
    markdown: str
