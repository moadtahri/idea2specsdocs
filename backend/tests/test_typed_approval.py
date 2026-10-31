import json
from typing import ClassVar

import pytest
from langchain.messages import AIMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

from app import quality_store as qs
from app import store, typed_approval
from app.agent import factory
from app.quality_models import BRIEF_FIELDS


@pytest.mark.parametrize(
    "text",
    ["approve", "Yes, save it!", "looks good, thanks", "LGTM", "ok", "Approved."],
)
def test_plain_approvals(text):
    assert typed_approval.is_approval(text)
    assert typed_approval.card_decisions(2, text) == [{"type": "approve"}] * 2


@pytest.mark.parametrize(
    "text",
    [
        "approve but rename the API",
        "no",
        "yes, after you add retention",
        "Make it shorter",
        "not yet",
    ],
)
def test_anything_else_requests_changes_with_the_words(text):
    assert not typed_approval.is_approval(text)
    assert typed_approval.card_decisions(1, text) == [
        {"type": "reject", "message": text}
    ]


def test_only_words_that_name_the_brief_approve_it():
    assert typed_approval.is_brief_approval("Approve the brief")
    assert typed_approval.is_brief_approval("I approve the project brief.")
    assert typed_approval.is_brief_approval("brief approved")
    for text in (
        "yes",
        "approve",
        "approve the brief but change the users",
        "don't approve the brief",
    ):
        assert not typed_approval.is_brief_approval(text)


def test_a_typed_brief_approval_goes_through_the_same_checks(client, project):
    assert typed_approval.approve_brief_from(project, "approve the brief") == (
        "There is no proposed brief to approve yet."
    )
    partial = client.put(
        f"/api/projects/{project}/brief", json={"vertical": "Clinics"}
    ).json()
    note = typed_approval.approve_brief_from(project, "approve the brief")
    assert note.startswith(
        "The app could not approve the brief: Resolve the brief's missing fields"
    )
    assert qs.brief_state(project)["status"] != "approved" and partial["revision"]
    client.put(
        f"/api/projects/{project}/brief",
        json={f: f"Confirmed {f}" for f in BRIEF_FIELDS},
    )
    assert typed_approval.approve_brief_from(project, "Approve the brief, thanks") == (
        "The app approved the brief from these words."
    )
    assert qs.brief_state(project)["status"] == "approved"
    assert typed_approval.approve_brief_from(project, "yes") is None


class Scripted(BaseChatModel):
    replies: ClassVar[list[AIMessage]] = []
    seen: ClassVar[list[list]] = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        Scripted.seen.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=Scripted.replies.pop(0))])


def write_prd(call_id):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "write_file",
                "args": {"file_path": "/docs/prd.md", "content": "# PRD\n"},
                "id": call_id,
            }
        ],
    )


def events(client, project, message):
    with client.stream(
        "POST", "/api/chat", json={"project_id": project, "message": message}
    ) as response:
        return [
            json.loads(line[5:])
            for line in response.iter_lines()
            if line.startswith("data:")
        ]


def test_typed_words_answer_the_waiting_card(client, project, monkeypatch):
    brief = {f: f"Confirmed {f}" for f in BRIEF_FIELDS}
    state = client.put(f"/api/projects/{project}/brief", json=brief).json()
    client.post(
        f"/api/projects/{project}/brief/approve", json={"revision": state["revision"]}
    )
    Scripted.replies[:] = [
        write_prd("w1"),
        AIMessage(content="Shorter now?"),  # after the change request
        write_prd("w2"),
        AIMessage(content="Saved the PRD."),
    ]
    Scripted.seen.clear()
    monkeypatch.setattr(factory, "build_llm", Scripted)
    prd = store.PROJECTS_DIR / project / "docs" / "prd.md"

    first = events(client, project, "Draft the PRD")
    assert any(e["type"] == "interrupt" for e in first) and not prd.exists()

    changes = events(client, project, "Make it shorter")
    assert any(
        e.get("text") == "Sending your changes for the waiting draft" for e in changes
    )
    rejected = [m for m in Scripted.seen[-1] if isinstance(m, ToolMessage)]
    assert (
        rejected and "Make it shorter" in str(rejected[-1].content) and not prd.exists()
    )

    again = events(client, project, "Try again")  # no card waits: an ordinary message
    assert any(e["type"] == "interrupt" for e in again)

    approved = events(client, project, "looks good, thanks")
    assert any(
        e.get("text") == "Saving: you approved the waiting draft" for e in approved
    )
    assert prd.read_text(encoding="utf-8") == "# PRD\n"
    assert not any(e["type"] == "error" for e in first + changes + again + approved)
