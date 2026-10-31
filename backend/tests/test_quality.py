"""Regression cases drawn from incomplete Canyas handover and discovery flows."""

import asyncio
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from app import quality, store
from app import quality_store as qs
from app.agent import factory, review
from app.agent.factory import scoped_env
from app.agent.requirements import RequirementsGate, SecurityCoverageFeedback
from app.quality_models import BRIEF_FIELDS, SKILL_IDS, ProjectBrief, ReviewDraft
from app.schemas import DOC_SLUGS


def complete_brief(client, project):
    brief = {field: f"Confirmed {field}" for field in BRIEF_FIELDS}
    brief.update(
        vertical="Partner marketing",
        service="Invite partners to publish customer stories",
    )
    state = client.put(f"/api/projects/{project}/brief", json=brief).json()
    assert (
        client.post(
            f"/api/projects/{project}/brief/approve",
            json={"revision": state["revision"]},
        ).status_code
        == 200
    )
    return state


def complete_docs(project):
    directory = store.PROJECTS_DIR / project / "docs"
    for slug in DOC_SLUGS:
        (directory / f"{slug}.md").write_text(
            f"# {slug}\nContract for approved service.\n", encoding="utf-8"
        )
    (directory / "prd.md").write_text(
        "FR-1: Partners may edit their own story; only admins may delete.\n",
        encoding="utf-8",
    )
    (directory / "security-blueprint.md").write_text(
        "SEC-1: Reject development bypass headers in production.\n", encoding="utf-8"
    )
    (directory / "qa-test-plan.md").write_text(
        "TC-1: Verify SEC-1 and FR-1 authorization, including negative cases.\n",
        encoding="utf-8",
    )
    return directory


def mock_reviewer(monkeypatch, findings=None, checks=SKILL_IDS):
    draft = ReviewDraft(
        summary="Reviewed all supplied contracts.",
        checks_completed=list(checks),
        findings=findings or [],
    )
    invoke = AsyncMock(
        return_value=AIMessage(
            content="",
            tool_calls=[
                {"name": "ReviewDraft", "args": draft.model_dump(), "id": "review"}
            ],
        )
    )
    monkeypatch.setattr(
        review,
        "build_llm",
        lambda: SimpleNamespace(
            bind_tools=lambda *args, **kwargs: SimpleNamespace(ainvoke=invoke)
        ),
    )
    return invoke


def test_vertical_and_service_are_required_for_brief_approval(client, project):
    brief = {
        field: "Confirmed"
        for field in BRIEF_FIELDS
        if field not in ("vertical", "service")
    }
    state = client.put(f"/api/projects/{project}/brief", json=brief).json()
    assert state["missing"] == ["vertical", "service"]
    assert (
        client.post(
            f"/api/projects/{project}/brief/approve",
            json={"revision": state["revision"]},
        ).status_code
        == 409
    )


def test_brief_approval_rejects_stale_version_and_open_questions(client, project):
    state = complete_brief(client, project)
    brief = {**state["brief"], "open_questions": ["Who may delete stories?"]}
    updated = client.put(f"/api/projects/{project}/brief", json=brief).json()
    for revision in (state["revision"], updated["revision"]):
        assert (
            client.post(
                f"/api/projects/{project}/brief/approve", json={"revision": revision}
            ).status_code
            == 409
        )


def test_proposed_defaults_are_not_confirmed_and_invalidate_cache(client, project):
    complete_brief(client, project)
    complete_docs(project)
    before = store.bundle_fingerprint(project)
    item = client.post(
        f"/api/projects/{project}/work-items",
        json={
            "kind": "product_decision",
            "title": "Version retention",
            "detail": "How long should versions be retained?",
            "proposal": "Indefinitely for MVP",
            "impact": "implementation",
            "affected_docs": ["prd", "database-schema"],
        },
    ).json()
    assert item["basis"] == "proposal" and item["status"] == "proposed"
    assert quality.assessment(project)["blocking"]["implementation"] == 1
    assert store.bundle_fingerprint(project) != before
    response = client.patch(
        f"/api/projects/{project}/work-items/{item['id']}",
        json={
            "status": "resolved",
            "resolution": "Keep versions for 90 days, then prune.",
        },
    )
    assert response.json()["basis"] == "user_confirmed"
    assert quality.assessment(project)["blocking"]["implementation"] == 0


def test_canyas_missing_named_gaps_and_security_tests_are_detected(client, project):
    directory = complete_docs(project)
    (directory / "security-blueprint.md").write_text(
        "G1–G5 must be addressed.\nG1: Disable dev headers.\nG2: Rate limit login.\nSEC-2: Limit invitations.\n",
        encoding="utf-8",
    )
    findings = quality.mechanical_findings(project)
    assert any("G3, G4, G5" in finding["detail"] for finding in findings)
    assert any("SEC-2 has no QA mapping" == finding["title"] for finding in findings)


def test_schwartz_exact_unmapped_controls_and_existing_links(client, project):
    directory = complete_docs(project)
    (directory / "security-blueprint.md").write_text(
        "\n".join(
            f"- SEC-{value:02d}: Required security behavior." for value in range(1, 9)
        ),
        encoding="utf-8",
    )
    (directory / "qa-test-plan.md").write_text(
        "| ID | Requirement | Steps | Expected |\n| --- | --- | --- | --- |\n"
        "| TC-14 | SEC-03 | Scan built client and start without key | No secrets; startup fails |\n"
        "| TC-15 | SEC-05 | Submit an injection payload | No instructions followed |\n"
        "| TC-16 | SEC-08 | Inspect HTTPS response headers | Required headers present |\n"
        "| TC-11 | FR-1 deletion | Delete then reload | Data removed |\n",
        encoding="utf-8",
    )
    state = client.get(f"/api/projects/{project}/quality").json()
    assert {
        row["control_id"] for row in state["security_coverage"] if not row["mapped"]
    } == {"SEC-01", "SEC-02", "SEC-04", "SEC-06", "SEC-07"}
    assert next(
        row for row in state["security_coverage"] if row["control_id"] == "SEC-05"
    )["test_ids"] == ["TC-15"]
    assert (
        len(
            [
                finding
                for finding in state["findings"]
                if finding["id"].startswith("security-test-")
            ]
        )
        == 5
    )
    assert "SEC-06 | UNMAPPED" in store.agent_bundle_markdown(project)


@pytest.mark.parametrize(
    "qa",
    [
        "SEC-1 will eventually be tested.\nTC-1: Functional happy path only.\n",
        "| Control | QA case |\n| SEC-1 | TC-99 |\nTC-1: Functional happy path only.\n",
    ],
)
def test_mentions_or_undefined_cases_are_not_security_coverage(client, project, qa):
    directory = complete_docs(project)
    (directory / "qa-test-plan.md").write_text(qa, encoding="utf-8")
    assert not quality.security_coverage(quality.documents(project))[0]["mapped"]


@pytest.mark.parametrize(
    "qa",
    [
        "## TC-1: Development bypass\nSetup: production config.\nSteps: submit X-User-Email without a token.\nExpected: SEC-1 rejects access.\n",
        "TC-1: Submit a production request without credentials; expect denial.\n\n## Control coverage\n| Control | QA case |\n| SEC-1 | TC-1 |\n",
    ],
)
def test_security_mapping_supports_case_blocks_and_traceability_tables(
    client, project, qa
):
    directory = complete_docs(project)
    (directory / "qa-test-plan.md").write_text(qa, encoding="utf-8")
    assert quality.security_coverage(quality.documents(project))[0]["test_ids"] == [
        "TC-1"
    ]


def test_deployment_placeholder_alone_is_not_an_implementation_block(client, project):
    directory = complete_docs(project)
    (directory / "devops-iac-spec.md").write_text(
        "Bucket name: TBD. Pass configured bucket through S3_BUCKET; reject missing value at startup.\n",
        encoding="utf-8",
    )
    findings = quality.mechanical_findings(project)
    assert findings and all(finding["severity"] != "blocker" for finding in findings)


@pytest.mark.parametrize(
    "name", ["write_file", "edit_file", "write_todos", "task", "execute"]
)
def test_unapproved_brief_blocks_planning_writing_and_specialists(
    client, project, name
):
    handler = AsyncMock()
    request = SimpleNamespace(
        tool_call={"id": "test", "name": name, "args": {"subagent_type": "architect"}}
    )
    with scoped_env(store.PROJECTS_DIR / project):
        result = asyncio.run(RequirementsGate().awrap_tool_call(request, handler))
    assert "vertical and service" in result.content
    handler.assert_not_awaited()


def test_unapproved_brief_still_lets_repo_reader_read_the_source(client, project):
    handler = AsyncMock(return_value="report")
    request = SimpleNamespace(
        tool_call={"id": "r", "name": "task", "args": {"subagent_type": "repo-reader"}}
    )
    with scoped_env(store.PROJECTS_DIR / project):
        assert (
            asyncio.run(RequirementsGate().awrap_tool_call(request, handler))
            == "report"
        )


def test_gate_allows_reading_then_approved_planning(client, project):
    handler = AsyncMock(return_value="allowed")
    with scoped_env(store.PROJECTS_DIR / project):
        request = SimpleNamespace(
            tool_call={"id": "read", "name": "read_file", "args": {}}
        )
        assert (
            asyncio.run(RequirementsGate().awrap_tool_call(request, handler))
            == "allowed"
        )
        complete_brief(client, project)
        request.tool_call["name"] = "write_todos"
        assert (
            asyncio.run(RequirementsGate().awrap_tool_call(request, handler))
            == "allowed"
        )


def test_factory_builds_graph_and_passes_vertical_context(client, project, monkeypatch):
    complete_brief(client, project)
    monkeypatch.setattr(
        factory, "build_llm", lambda: ChatOpenAI(api_key="test", model="test")
    )

    async def build():
        graph, manager = await factory.build_agent(
            store.PROJECTS_DIR / project, store.checkpoint_path(project)
        )
        assert graph is not None
        await manager.__aexit__(None, None, None)

    asyncio.run(build())


def test_graph_exposes_only_discovery_tools_before_approval(
    client, project, monkeypatch
):
    class DiscoveryModel(BaseChatModel):
        exposed: ClassVar[list[list[str]]] = []

        @property
        def _llm_type(self):
            return "discovery-test"

        def bind_tools(self, tools, **kwargs):
            self.exposed.append(
                [tool.name if hasattr(tool, "name") else tool["name"] for tool in tools]
            )
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="Which service will your app provide?"
                        )
                    )
                ]
            )

    monkeypatch.setattr(factory, "build_llm", DiscoveryModel)

    async def run():
        directory = store.PROJECTS_DIR / project
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                await graph.ainvoke(
                    {"messages": [("user", "Plan my app")]},
                    {"configurable": {"thread_id": project}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    asyncio.run(run())
    assert DiscoveryModel.exposed
    exposed = set(DiscoveryModel.exposed[-1])
    assert {"read_file", "propose_project_brief", "get_project_context"} <= exposed
    assert not {"write_file", "edit_file", "write_todos"} & exposed
    assert (
        "task" in exposed
    )  # for repo-reader only: the gate refuses the other specialists (spec 04)


def test_review_is_independent_and_stale_after_changes(client, project, monkeypatch):
    complete_brief(client, project)
    directory = complete_docs(project)
    invoke = mock_reviewer(monkeypatch)
    report = client.post(f"/api/projects/{project}/reviews", json={}).json()
    assert report["status"] == "complete"
    state = quality.assessment(project)
    assert state["ready_for_implementation"] and not state["implementation_verified"]
    assert not quality.assessment(project, "staging")["ready_for_implementation"]
    assert "Partner marketing" in str(invoke.call_args)
    (directory / "prd.md").write_text("FR-1: New behavior.\n", encoding="utf-8")
    assert quality.assessment(project)["review_status"] == "outdated"
    assert not quality.assessment(project)["ready_for_implementation"]


@pytest.mark.parametrize("invalid", ["citation", "checklist"])
def test_incomplete_reviews_cannot_promote_readiness(
    client, project, monkeypatch, invalid
):
    complete_brief(client, project)
    complete_docs(project)
    finding = {
        "category": "product-completeness",
        "severity": "blocker",
        "impact": "implementation",
        "title": "Search scope unclear",
        "detail": "Scope is not agreed.",
        "recommendation": "Confirm search scope.",
        "affected_docs": ["prd"],
        "citations": [
            {"slug": "prd", "line": 1, "quote": "This is not in the supplied document"}
        ],
    }
    mock_reviewer(
        monkeypatch,
        findings=[finding] if invalid == "citation" else [],
        checks=SKILL_IDS if invalid == "citation" else SKILL_IDS[:2],
    )
    report = client.post(f"/api/projects/{project}/reviews", json={}).json()
    assert report["status"] == "incomplete" and report["errors"]
    assert not quality.assessment(project)["ready_for_implementation"]


def test_supported_semantic_ambiguity_blocks_implementation(
    client, project, monkeypatch
):
    complete_brief(client, project)
    directory = complete_docs(project)
    (directory / "prd.md").write_text(
        "FR-1: Retention policy is an open product question.\n", encoding="utf-8"
    )
    finding = {
        "category": "product-completeness",
        "severity": "blocker",
        "impact": "implementation",
        "title": "Retention unresolved",
        "detail": "The product decision affects storage and pruning.",
        "recommendation": "Ask the owner to decide.",
        "affected_docs": ["prd", "database-schema"],
        "citations": [
            {
                "slug": "prd",
                "line": 1,
                "quote": "Retention policy is an open product question.",
            }
        ],
    }
    mock_reviewer(monkeypatch, [finding])
    client.post(f"/api/projects/{project}/reviews", json={})
    state = quality.assessment(project)
    assert state["review_current"] and not state["ready_for_implementation"]
    assert "Retention unresolved" in store.agent_bundle_markdown(project)


def test_evidence_requires_real_project_artifact_and_is_revision_bound(
    client, project, monkeypatch
):
    complete_brief(client, project)
    directory = complete_docs(project)
    mock_reviewer(monkeypatch)
    data = {
        "scope": "implementation",
        "environment": "test",
        "source_revision": "abc123",
        "outcome": "passed",
        "command": "pytest",
        "summary": "Authorization test passed",
        "attachment_id": "absent",
        "covered_ids": ["TC-1"],
        "attested": True,
    }
    url = f"/api/projects/{project}"
    assert client.post(f"{url}/evidence", json=data).status_code == 422
    uploaded = client.post(
        f"{url}/uploads", files={"file": ("results.txt", b"TC-1 passed", "text/plain")}
    ).json()
    data["attachment_id"] = uploaded["attachment_id"]
    assert client.post(f"{url}/evidence", json=data).status_code == 201
    client.post(f"{url}/reviews", json={})
    state = quality.assessment(project)
    assert state["implementation_verified"] and not state["ready_for_production"]
    # A newer failure overrides the earlier passing report.
    client.post(f"{url}/evidence", json={**data, "outcome": "failed"})
    client.post(f"{url}/reviews", json={})
    assert not quality.assessment(project)["implementation_verified"]
    (directory / "prd.md").write_text("FR-1: Changed requirements.\n", encoding="utf-8")
    client.post(f"{url}/reviews", json={})
    assert not quality.assessment(project)["implementation_verified"]


def test_saved_security_or_qa_write_automatically_returns_coverage_feedback(
    client, project
):
    from langchain.messages import ToolMessage

    directory = complete_docs(project)
    request = SimpleNamespace(
        tool_call={
            "id": "save",
            "name": "edit_file",
            "args": {"file_path": "/docs/qa-test-plan.md"},
        }
    )

    async def save_unmapped(_):
        (directory / "qa-test-plan.md").write_text(
            "TC-1: General happy path.\n", encoding="utf-8"
        )
        return ToolMessage(content="Saved", tool_call_id="save")

    async def save_mapped(_):
        (directory / "qa-test-plan.md").write_text(
            "TC-1: Send development header, SEC-1 must deny access.\n", encoding="utf-8"
        )
        return ToolMessage(content="Saved", tool_call_id="save")

    with scoped_env(directory.parent):
        missing = asyncio.run(
            SecurityCoverageFeedback().awrap_tool_call(request, save_unmapped)
        )
        assert "Unmapped controls: SEC-1" in missing.content
        assert "Saved" in missing.content
        mapped = asyncio.run(
            SecurityCoverageFeedback().awrap_tool_call(request, save_mapped)
        )
        assert "traceability only" in mapped.content
        assert "not test adequacy or execution" in mapped.content


def test_delete_removes_quality_register(client, project):
    qs.propose_brief(
        project, ProjectBrief(vertical="Booking", service="Book consultations")
    )
    assert qs.rows(project, "brief")
    assert client.delete(f"/api/projects/{project}").status_code == 204
    assert not qs.rows(project, "brief")


def test_review_arguments_sent_as_json_text_are_decoded():
    # The model sends lists as JSON text (spec 07): decode before validating, as propose_work_item does.
    import json

    args = {
        "summary": "Two gaps.",
        "checks_completed": json.dumps(list(SKILL_IDS)),
        "findings": json.dumps(
            [
                {
                    "category": "product-completeness",
                    "severity": "warning",
                    "impact": "implementation",
                    "title": "No cancel window",
                    "detail": "The PRD does not say when owners may cancel.",
                    "recommendation": "Decide the window.",
                    "affected_docs": ["prd"],
                    "citations": [{"slug": "prd", "line": 3, "quote": "Owners cancel"}],
                }
            ]
        ),
    }
    draft = ReviewDraft.model_validate(review.decoded(args))
    assert (
        draft.checks_completed == list(SKILL_IDS)
        and draft.findings[0].citations[0].line == 3
    )
    assert review.decoded("[not json") == "[not json"
