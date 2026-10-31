"""Reply ratings and Stop (spec 09)."""

import asyncio

from app import main, store


def test_a_reply_is_rated_once_found_again_and_withdrawn(client, project):
    reply = "  Here is the plan.\n"
    first = client.post(
        f"/api/projects/{project}/feedback",
        json={"rating": "good", "reply": reply, "prompt": "Plan it"},
    )
    assert first.status_code == 201 and first.json()["reply_hash"] == store.reply_hash(
        "Here is the plan."
    )
    bad = {
        "rating": "bad",
        "reply": reply,
        "reasons": ["too_long", "other"],
        "note": "Shorter, please.",
    }
    client.post(
        f"/api/projects/{project}/feedback", json=bad
    )  # the same reply: replaced, not added
    rows = client.get(f"/api/projects/{project}/feedback").json()["ratings"]
    assert rows == [
        {
            "reply_hash": store.reply_hash(reply),
            "rating": "bad",
            "reasons": ["too_long", "other"],
        }
    ]
    assert (
        client.delete(
            f"/api/projects/{project}/feedback/{store.reply_hash(reply)}"
        ).status_code
        == 204
    )
    assert client.get(f"/api/projects/{project}/feedback").json()["ratings"] == []
    assert (
        client.post(
            f"/api/projects/{project}/feedback", json={"rating": "meh", "reply": "x"}
        ).status_code
        == 422
    )


def test_stop_cancels_the_running_turn_only(client, project):
    assert client.post(f"/api/projects/{project}/stop").json() == {"stopped": False}

    async def run():
        task = asyncio.create_task(asyncio.sleep(30))
        main._chat_tasks[project] = task
        try:
            return main.stop_turn(project), task
        finally:
            main._chat_tasks.pop(project, None)

    result, task = asyncio.run(run())
    assert result == {"stopped": True} and task.cancelled()
    assert client.post("/api/projects/does-not-exist/stop").status_code == 404
