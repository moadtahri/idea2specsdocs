"""The conversation survives a reload (spec 08): what the user saw, the waiting card, the to-dos."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain.messages import AIMessageChunk

from app import main, store

CARD = {
    "action_requests": [
        {"name": "write_file", "args": {"file_path": "/docs/prd.md", "content": "FR-1"}}
    ],
    "review_configs": [],
}


def stub(monkeypatch, runs):
    """Each chat request plays the next run: a reply, then optionally a card and to-dos."""
    script = iter(runs)

    class Agent:
        async def aget_state(self, config):
            return SimpleNamespace(interrupts=())

        async def astream(self, value, **kwargs):
            text, card, todos = next(script)
            yield ((), "messages", (AIMessageChunk(content=text), {}))
            yield (
                ("tools:specialist",),
                "messages",
                (AIMessageChunk(content="specialist notes"), {}),
            )
            if todos:
                yield ((), "values", {"todos": todos})
            if card:
                yield (
                    (),
                    "updates",
                    {"__interrupt__": [SimpleNamespace(id="card-1", value=card)]},
                )

    async def build(*args):
        return Agent(), SimpleNamespace(__aexit__=AsyncMock())

    monkeypatch.setattr(main, "build_agent", build)


def test_a_reload_shows_the_conversation_the_card_and_the_todos(
    client, project, monkeypatch
):
    todos = [{"content": "Draft the PRD", "status": "in_progress"}]
    stub(
        monkeypatch,
        [("Here is the PRD.", CARD, todos), ("Saved. Next, the spike.", None, None)],
    )
    client.post(
        "/api/chat",
        json={"project_id": project, "message": "Draft it", "message_id": "m1"},
    )
    saved = client.get(f"/api/projects/{project}/history").json()
    assert saved["messages"] == [
        {"id": "m1", "role": "user", "text": "Draft it"},
        {
            "id": "m1-reply",
            "role": "agent",
            "text": "Here is the PRD.",
        },  # never a specialist's notes
    ]
    assert saved["pending"]["action_requests"][0]["args"]["file_path"] == "/docs/prd.md"
    assert saved["todos"] == todos

    client.post(
        "/api/chat",
        json={
            "project_id": project,
            "resume": [{"type": "approve"}],
            "message_id": "m2",
        },
    )
    after = client.get(f"/api/projects/{project}/history").json()
    assert [m["text"] for m in after["messages"][2:]] == [
        "✅ Approved: PRD",
        "Saved. Next, the spike.",
    ]
    assert after["pending"] is None  # the card was answered


def test_a_resend_is_recorded_once_and_attachments_are_named(
    client, project, monkeypatch
):
    stub(
        monkeypatch,
        [("First answer.", None, None), ("Same request again.", None, None)],
    )
    upload = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("notes.txt", b"A booking app.", "text/plain")},
    ).json()
    body = {
        "project_id": project,
        "message": "Read this",
        "message_id": "m1",
        "attachment_ids": [upload["attachment_id"]],
    }
    client.post("/api/chat", json=body)
    client.post(
        "/api/chat", json=body
    )  # Resend after a dropped connection: same message id
    messages = client.get(f"/api/projects/{project}/history").json()["messages"]
    assert [m["text"] for m in messages] == [
        "Read this\n\nAttached: notes.txt",
        "First answer.",
    ]


def test_changes_requested_and_deleting_the_project(client, project, monkeypatch):
    stub(monkeypatch, [("Draft ready.", CARD, None), ("Shorter now.", CARD, None)])
    client.post(
        "/api/chat",
        json={"project_id": project, "message": "Draft it", "message_id": "m1"},
    )
    client.post(
        "/api/chat",
        json={
            "project_id": project,
            "resume": [{"type": "reject", "message": "Make it shorter"}],
            "message_id": "m2",
        },
    )
    saved = client.get(f"/api/projects/{project}/history").json()
    assert (
        saved["messages"][2]["text"] == "✏️ Changes requested for PRD: Make it shorter"
    )
    assert saved["pending"] is not None  # the revised draft waits on a new card
    assert client.delete(f"/api/projects/{project}").status_code == 204
    assert store.chat_history(project) == {"messages": [], "pending": None, "todos": []}


def test_each_step_of_wizi_starts_a_new_paragraph(client, project, monkeypatch):
    class Agent:
        async def aget_state(self, config):
            return SimpleNamespace(interrupts=())

        async def astream(self, value, **kwargs):
            for message_id, text in (
                ("a", "Got it, a salon."),
                ("a", " Booking online."),
                ("b", "Working out the choices."),
            ):
                yield (
                    (),
                    "messages",
                    (AIMessageChunk(content=text, id=message_id), {}),
                )

    async def build(*args):
        return Agent(), SimpleNamespace(__aexit__=AsyncMock())

    monkeypatch.setattr(main, "build_agent", build)
    client.post(
        "/api/chat", json={"project_id": project, "message": "Hi", "message_id": "m1"}
    )
    reply = client.get(f"/api/projects/{project}/history").json()["messages"][1]["text"]
    assert reply == "Got it, a salon. Booking online.\n\nWorking out the choices."
