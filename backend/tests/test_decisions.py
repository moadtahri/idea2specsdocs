from app import quality_store as qs
from app.quality_models import ItemResolution, WorkItemInput


def propose(project, title, **extra):
    return qs.propose_item(
        project,
        WorkItemInput(
            kind="product_decision",
            title=title,
            detail=f"Decide {title.lower()}.",
            affected_docs=["prd"],
            **extra,
        ),
    )


def test_items_default_to_stakeholder_owned_with_no_blockers(client, project):
    item = propose(project, "Appointment types")
    assert item.owner_type == "stakeholder" and item.blocked_by == []


def test_a_blocker_must_exist_before_the_item_it_blocks(client, project):
    response = client.post(
        f"/api/projects/{project}/work-items",
        json={
            "kind": "product_decision",
            "title": "Cancellation rules",
            "detail": "Who may cancel a booking.",
            "affected_docs": ["prd"],
            "blocked_by": ["DEC-missing"],
        },
    )
    assert response.status_code == 422
    assert "Record a blocker before" in response.json()["detail"]


def test_frontier_is_open_items_whose_blockers_are_resolved(client, project):
    types = propose(project, "Appointment types", proposal="Three short types")
    vets = propose(
        project, "Vet choice", owner_type="default", proposal="First available"
    )
    slots = propose(project, "Slot lengths", blocked_by=[types.id])
    reminders = propose(project, "Reminders", blocked_by=[types.id, vets.id])
    work = qs.items(project)
    assert qs.frontier(work) == [types.id, vets.id]

    qs.resolve_item(
        project, types.id, ItemResolution(status="resolved", resolution="Three")
    )
    qs.resolve_item(
        project, vets.id, ItemResolution(status="deferred", resolution="Later")
    )
    assert qs.frontier(qs.items(project)) == [
        slots.id
    ]  # a deferred blocker keeps Reminders waiting
    assert reminders.id not in qs.frontier(qs.items(project))


def test_quality_state_lists_the_frontier(client, project):
    first = propose(project, "Appointment types")
    propose(project, "Slot lengths", blocked_by=[first.id])
    state = client.get(f"/api/projects/{project}/quality").json()
    assert state["frontier"] == [first.id]
    assert {item["owner_type"] for item in state["items"]} == {"stakeholder"}


def test_a_plain_yes_takes_the_proposal_and_keeps_the_users_words(client, project):
    item = propose(project, "Vet choice", proposal="First available, optional vet")
    settled = qs.settle_item(project, item.id, "Yes", "", "yes, go with all of those")
    assert settled.status == "resolved" and settled.basis == "user_answered"
    assert settled.resolution == "First available, optional vet"
    assert settled.answered_with == "Yes"


def test_words_must_be_the_users_own_and_whole(client, project):
    import pytest

    item = propose(project, "Vet choice", proposal="First available")
    with pytest.raises(ValueError, match="not in the user's latest message"):
        qs.settle_item(project, item.id, "yes", "", "I'll tell you yesterday's numbers")
    with pytest.raises(ValueError, match="not in the user's latest message"):
        qs.settle_item(project, item.id, "first available", "", "What do you suggest?")
    explicit = qs.settle_item(
        project,
        item.id,
        "owners  pick the VET",
        "Owners pick the vet",
        "Owners pick the vet.",
    )
    assert explicit.resolution == "Owners pick the vet"
    with pytest.raises(ValueError, match="already resolved"):
        qs.settle_item(project, item.id, "yes", "", "yes")


def test_repo_facts_and_items_without_a_proposal_are_not_settled_by_yes(
    client, project
):
    import pytest

    fact = propose(project, "Current framework", owner_type="repo", proposal="Django")
    with pytest.raises(ValueError, match="fact to look up"):
        qs.settle_item(project, fact.id, "yes", "", "yes")
    bare = propose(project, "Opening hours")
    with pytest.raises(ValueError, match="no proposal"):
        qs.settle_item(project, bare.id, "yes", "", "yes")


def test_settle_decision_reads_the_latest_user_message_in_a_real_run(
    client, project, monkeypatch
):
    import asyncio
    from typing import ClassVar

    from langchain.messages import AIMessage, ToolMessage
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    from app import store
    from app.agent import factory
    from app.agent.factory import scoped_env

    item = propose(project, "Vet choice", proposal="First available")
    other = propose(project, "Reminders", proposal="Email the day before")

    class Model(BaseChatModel):
        replies: ClassVar[list] = []

        @property
        def _llm_type(self):
            return "settle-test"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[ChatGeneration(message=Model.replies.pop(0))]
            )

    Model.replies[:] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "settle_decision",
                    "args": {"item_id": item.id, "user_words": "yes"},
                    "id": "a",
                },
                {
                    "name": "settle_decision",
                    "args": {"item_id": other.id, "user_words": "by SMS"},
                    "id": "b",
                },
            ],
        ),
        AIMessage(content="Settled the vet choice."),
    ]
    monkeypatch.setattr(factory, "build_llm", Model)

    async def run():
        directory = store.PROJECTS_DIR / project
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                return await graph.ainvoke(
                    {"messages": [("user", "Yes to the vet choice recommendation.")]},
                    {"configurable": {"thread_id": project}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    state = asyncio.run(run())
    results = {
        m.tool_call_id: m for m in state["messages"] if isinstance(m, ToolMessage)
    }
    assert results["a"].status != "error"
    assert (
        results["b"].status == "error"
        and "not in the user's latest message" in results["b"].content
    )
    statuses = {i.id: i.status for i in qs.items(project)}
    assert statuses == {item.id: "resolved", other.id: "proposed"}


def test_the_tool_takes_flat_arguments_as_the_model_sends_them(client, project):
    # Shapes from spec 07's first live run, where every save failed under the old single `item` argument.
    from app import store
    from app.agent import tools
    from app.agent.factory import scoped_env

    with scoped_env(store.PROJECTS_DIR / project):
        first = tools.propose_work_item.invoke(
            {
                "affected_docs": '["sad-architecture", "security-blueprint"]',
                "detail": "Which SMS account should send the day-before reminders?",
                "impact": "implementation",
                "kind": "product_decision",
                "owner_type": "stakeholder",
                "proposal": "Twilio from the salon's account",
                "title": "SMS provider",
            }
        )
        second = tools.propose_work_item.invoke(
            {
                "affected_docs": ["prd"],
                "detail": "At what local time does the reminder go out?",
                "kind": "product_decision",
                "title": "Reminder time",
                "blocked_by": first["id"],
            }
        )
    assert first["affected_docs"] == ["sad-architecture", "security-blueprint"]
    assert second["blocked_by"] == [first["id"]]
    assert {i.title for i in qs.items(project)} == {"SMS provider", "Reminder time"}
