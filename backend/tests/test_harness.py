import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.errors import GraphInterrupt

from app import quality_store as qs
from app import store
from app.agent import factory, harness
from app.agent.factory import scoped_env


def call(name="propose_project_brief", call_id="1", **args):
    return SimpleNamespace(tool_call={"name": name, "id": call_id, "args": args})


def ok(request):
    return ToolMessage(content="saved", tool_call_id=request.tool_call["id"])


def broken(request):
    raise ValueError("brief is missing its vertical")


def test_raising_tool_answers_with_an_error_instead_of_ending_the_turn():
    breaker = harness.RepeatFailureBreaker(3)
    result = breaker.wrap_tool_call(call(), broken)
    assert result.status == "error"
    assert "brief is missing its vertical" in result.content


def test_identical_failed_call_is_refused_without_running():
    breaker = harness.RepeatFailureBreaker(3)
    breaker.wrap_tool_call(call(vertical="x"), broken)
    ran = []
    result = breaker.wrap_tool_call(
        call(call_id="2", vertical="x"), lambda r: ran.append(r) or ok(r)
    )
    assert not ran
    assert result.status == "error" and "already failed" in result.content
    # Different arguments may still run.
    assert breaker.wrap_tool_call(call(call_id="3", vertical="y"), ok).status != "error"


def test_tool_that_failed_too_often_is_refused_for_any_arguments():
    breaker = harness.RepeatFailureBreaker(2)
    breaker.wrap_tool_call(call(n=1), broken)
    breaker.wrap_tool_call(call(n=2), broken)
    result = breaker.wrap_tool_call(call(n=3), ok)
    assert result.status == "error" and "failed 2 times" in result.content


def test_a_change_clears_the_record_of_failed_calls_but_a_read_does_not():
    breaker = harness.RepeatFailureBreaker(3)
    breaker.wrap_tool_call(call(vertical="x"), broken)
    breaker.wrap_tool_call(call("get_project_context"), ok)
    assert breaker.wrap_tool_call(call(vertical="x"), ok).status == "error"
    breaker.wrap_tool_call(call("propose_work_item", item={}), ok)
    assert breaker.wrap_tool_call(call(vertical="x"), ok).status != "error"


def test_user_approved_writes_are_never_refused():
    breaker = harness.RepeatFailureBreaker(1)
    breaker.wrap_tool_call(call("write_file", file_path="/docs/prd.md"), broken)
    result = breaker.wrap_tool_call(call("write_file", file_path="/docs/prd.md"), ok)
    assert result.status != "error"


def test_new_run_starts_with_a_clean_record():
    breaker = harness.RepeatFailureBreaker(3)
    breaker.wrap_tool_call(call(vertical="x"), broken)
    asyncio.run(breaker.abefore_agent({}, None))
    assert breaker.wrap_tool_call(call(vertical="x"), ok).status != "error"


def test_pauses_for_the_user_pass_through():
    def pause(request):
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        harness.RepeatFailureBreaker(3).wrap_tool_call(call(), pause)


def test_async_tool_failure_is_converted_too():
    async def failing(request):
        raise RuntimeError("store locked")

    result = asyncio.run(
        harness.RepeatFailureBreaker(3).awrap_tool_call(call(), failing)
    )
    assert result.status == "error" and "store locked" in result.content


def test_turn_limit_ends_with_a_message_the_user_can_act_on():
    limit = harness.TurnLimit(run_limit=2, exit_behavior="end")
    assert limit.before_model({"run_model_call_count": 1}, None) is None
    result = limit.before_model({"run_model_call_count": 2}, None)
    assert result["jump_to"] == "end"
    [message] = result["messages"]
    assert harness.from_harness(message)
    assert "continue" in message.content and "limit (" not in message.content


def test_limits_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_MODEL_CALLS", "7")
    monkeypatch.setenv("AGENT_MAX_TOOL_FAILURES", "not a number")
    limit, _tools, breaker = harness.breakers()
    assert limit.run_limit == 7
    assert breaker.max_failures == 3


@pytest.mark.parametrize(
    ("problem", "retry"),
    [
        (SimpleNamespace(status_code=429), True),
        (SimpleNamespace(status_code=503), True),
        (SimpleNamespace(status_code=401), False),
        (SimpleNamespace(status_code=400), False),
        (type("APIConnectionError", (Exception,), {})(), True),
        (ValueError("bad"), False),
    ],
)
def test_only_transient_model_errors_are_retried(problem, retry):
    assert harness.transient(problem) is retry


def test_fallback_model_is_added_only_when_given():
    assert len(harness.resilience()) == 1
    assert len(harness.resilience(fallback_model=object())) == 2


def test_empty_summary_is_replaced_by_a_digest_of_the_exchange():
    folded = [
        HumanMessage(content="We need a booking app for clinics"),
        AIMessage(
            content="",
            tool_calls=[{"name": "propose_project_brief", "args": {}, "id": "1"}],
        ),
        harness.harness_message("I reached this turn's work limit"),
        AIMessage(content="Brief proposed."),
    ]
    summary = harness.checked_summary(
        folded, "Previous conversation was too long to summarize."
    )
    assert "User: We need a booking app for clinics" in summary
    assert "(wizi used: propose_project_brief)" in summary
    assert "work limit" not in summary
    assert harness.checked_summary(folded, "A real summary.") == "A real summary."


def test_digest_keeps_the_newest_lines_within_its_cap(monkeypatch):
    monkeypatch.setattr(harness, "DIGEST_CHARS", 20)
    digest = harness.conversation_digest(
        [HumanMessage(content="early " * 5), HumanMessage(content="newest")]
    )
    assert "User: newest" in digest and "User: early" not in digest


def captured_agent(monkeypatch, project):
    captured = {}
    monkeypatch.setattr(factory, "build_llm", lambda: ScriptedModel())
    monkeypatch.setattr(
        factory,
        "create_deep_agent",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    async def build():
        _graph, manager = await factory.build_agent(
            store.PROJECTS_DIR / project, store.checkpoint_path(project)
        )
        await manager.__aexit__(None, None, None)

    asyncio.run(build())
    return captured


def names(middleware):
    return [m.name for m in middleware]


def test_wizi_and_every_specialist_run_with_their_own_breakers(
    client, project, monkeypatch
):
    captured = captured_agent(monkeypatch, project)
    main = names(captured["middleware"])
    for name in (
        "TurnLimit",
        "ToolCallLimitMiddleware",
        "RepeatFailureBreaker",
        "ModelRetryMiddleware",
    ):
        assert name in main
    assert "ModelFallbackMiddleware" not in main  # MODEL_FALLBACK_NAME is not set
    assert {"SummarizationMiddleware", "SummarizationToolMiddleware"} <= set(main)
    breakers = {
        id(m) for m in captured["middleware"] if m.name == "RepeatFailureBreaker"
    }
    for specialist in captured["subagents"]:
        own = [m for m in specialist["middleware"] if m.name == "RepeatFailureBreaker"]
        assert len(own) == 1 and id(own[0]) not in breakers
        breakers.add(id(own[0]))
        assert "TurnLimit" in names(specialist["middleware"])


def test_compaction_uses_the_harness_settings(client, project, monkeypatch):
    captured = captured_agent(monkeypatch, project)
    [compaction] = [
        m for m in captured["middleware"] if isinstance(m, factory.Compaction)
    ]
    assert compaction.name == "SummarizationMiddleware"
    folded = [HumanMessage(content="Plan a clinic booking app")]
    assert "clinic booking" in harness.checked_summary(
        folded, "No previous conversation history."
    )


class ScriptedModel(BaseChatModel):
    """First proposes a malformed brief (the tool raises), then asks a question."""

    replies: ClassVar[list[AIMessage]] = []
    exposed: ClassVar[list[list[str]]] = []
    seen: ClassVar[list[list]] = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        ScriptedModel.exposed.append(
            [tool.name if hasattr(tool, "name") else tool["name"] for tool in tools]
        )
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        ScriptedModel.seen.append(list(messages))
        return ChatResult(
            generations=[ChatGeneration(message=ScriptedModel.replies.pop(0))]
        )


def test_a_raising_tool_no_longer_ends_the_turn(client, project, monkeypatch):
    # Bad arguments already come back as tool errors; anything else a tool raises used to end the turn.
    def locked(*args, **kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(qs, "propose_brief", locked)
    ScriptedModel.exposed.clear()
    ScriptedModel.seen.clear()
    ScriptedModel.replies[:] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "propose_project_brief",
                    "args": {"brief": {"vertical": "Clinics"}},
                    "id": "c1",
                }
            ],
        ),
        AIMessage(content="Which service will your app provide?"),
    ]
    monkeypatch.setattr(factory, "build_llm", ScriptedModel)

    async def run():
        directory = store.PROJECTS_DIR / project
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                return await graph.ainvoke(
                    {"messages": [("user", "Plan my app")]},
                    {"configurable": {"thread_id": project}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    state = asyncio.run(run())
    [failure] = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert failure.status == "error" and "database is locked" in failure.content
    assert state["messages"][-1].content == "Which service will your app provide?"
    assert "compact_conversation" in ScriptedModel.exposed[-1]


def test_turn_limit_message_reaches_the_chat_once(client, project, monkeypatch):
    import json
    from unittest.mock import AsyncMock

    from app import main

    limit = harness.harness_message(
        "I reached this turn's work limit before finishing."
    )

    class Agent:
        async def aget_state(self, config):
            return SimpleNamespace(interrupts=())  # no card waits

        async def astream(self, *args, **kwargs):
            yield (
                (),
                "updates",
                {"model": {"messages": [AIMessage(content="Drafting.")]}},
            )
            yield (
                ("tools:qa",),
                "updates",
                {"TurnLimit.before_model": {"messages": [limit]}},
            )
            yield ((), "updates", {"TurnLimit.before_model": {"messages": [limit]}})

    async def build(*args):
        return Agent(), SimpleNamespace(__aexit__=AsyncMock())

    monkeypatch.setattr(main, "build_agent", build)
    response = client.post(
        "/api/chat", json={"project_id": project, "message": "Draft it"}
    )
    events = [
        json.loads(line[5:])
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    tokens = [event["text"] for event in events if event["type"] == "token"]
    assert tokens == ["I reached this turn's work limit before finishing."]
    assert events[-1]["type"] == "done"
