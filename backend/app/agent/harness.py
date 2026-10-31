"""Harness middleware: per-run limits, the tool-failure breaker, model retries and the compaction digest.

Ported from the Canyas director harness (``director/breakers.py`` and ``agent.py``). Its tools return a JSON
envelope; ours raise, so a failure here is a ``ToolMessage`` with ``status == "error"``. The summarization
middleware itself is assembled in ``factory.py``, the only module that imports deepagents.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.types import hook_config
from langchain.messages import AIMessage, ToolMessage

logger = logging.getLogger(__name__)

# Messages the harness adds for the user; main.py forwards them as chat text.
HARNESS_SOURCE = "harness"
# They run only after the user approved them on a card: their decision, never refused by the breaker.
APPROVED_TOOLS = frozenset({"write_file", "edit_file"})
# A success of these changes nothing, so it keeps the record of failed calls.
READ_ONLY_TOOLS = frozenset(
    {
        "ls",
        "glob",
        "grep",
        "read_file",
        "write_todos",
        "list_docs",
        "get_project_context",
        "load_review_skill",
        "check_bundle_contracts",
        "check_package",
        "estimate_cost",
    }
)

# Compaction (Canyas KH-8). The library default waits for 170k tokens and keeps 6 messages when the model has no
# context profile, so every call paid for the whole chat. Decisions survive outside the chat: the brief, the
# decision register and the documents are files the tools read back.
COMPACT_AT_TOKENS = 80_000
KEEP_MESSAGES = 24
CLIP_ARGS_AT_TOKENS = 50_000
CLIP_ARGS_MAX_CHARS = 2_000
# What LangChain's summarizer returns instead of a summary when it had nothing to send the model.
EMPTY_SUMMARIES = frozenset(
    {
        "Previous conversation was too long to summarize.",
        "No previous conversation history.",
    }
)
DIGEST_CHARS = 12_000


def setting(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        logger.warning("%s is not a whole number; using %s", name, default)
        return default


def harness_message(text: str) -> AIMessage:
    return AIMessage(content=text, additional_kwargs={"itos_source": HARNESS_SOURCE})


def from_harness(message: Any) -> bool:
    return (getattr(message, "additional_kwargs", None) or {}).get(
        "itos_source"
    ) == HARNESS_SOURCE


class TurnLimit(ModelCallLimitMiddleware):
    """End the run at the model-call limit with a message the user can act on, not the library's counter text."""

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime) -> dict[str, Any] | None:
        result = super().before_model(state, runtime)
        if result and result.get("jump_to") == "end":
            logger.warning("turn limit reached: %s", result["messages"][0].content)
            result["messages"] = [
                harness_message(
                    "I reached this turn's work limit before finishing. Everything you approved is saved. "
                    'Reply "continue" and I will pick up where I stopped.'
                )
            ]
        return result


def failed(result: Any) -> bool:
    return isinstance(result, ToolMessage) and result.status == "error"


class RepeatFailureBreaker(AgentMiddleware):
    """Per run: refuse a call identical to one that failed, or any call to a tool that failed ``max_failures``
    times; a tool that raises answers with an error result instead of ending the turn. An instruction not to
    retry is not a breaker (Canyas, the "loop trap")."""

    def __init__(self, max_failures: int):
        super().__init__()
        self.max_failures = max_failures
        self._failed_calls: set[str] = set()
        self._failures: dict[str, int] = {}

    def before_agent(self, state, runtime) -> None:
        self._failed_calls.clear()  # a new run starts with a clean record
        self._failures.clear()

    async def abefore_agent(self, state, runtime) -> None:
        return self.before_agent(state, runtime)

    @staticmethod
    def _key(call: dict) -> str:
        return call["name"] + json.dumps(
            call.get("args") or {}, sort_keys=True, default=str
        )

    def _blocked(self, call: dict) -> ToolMessage | None:
        if call["name"] in APPROVED_TOOLS:
            return None
        reason = None
        if self._key(call) in self._failed_calls:
            reason = "this exact call already failed in this turn"
        elif self._failures.get(call["name"], 0) >= self.max_failures:
            reason = f"{call['name']} has failed {self._failures[call['name']]} times in this turn"
        if reason is None:
            return None
        return ToolMessage(
            content=f"Not run: {reason}. Tell the user what failed and ask how to proceed instead of retrying.",
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )

    def _record(self, call: dict, result: Any) -> None:
        if failed(result):
            logger.warning(
                "tool %s failed: %s", call["name"], str(result.content)[:500]
            )
            self._failed_calls.add(self._key(call))
            self._failures[call["name"]] = self._failures.get(call["name"], 0) + 1
        elif isinstance(result, ToolMessage) and call["name"] not in READ_ONLY_TOOLS:
            # Something changed (a brief proposed, a document saved): the same call may now succeed.
            self._failed_calls.clear()

    @staticmethod
    def _crashed(call: dict, problem: Exception) -> ToolMessage:
        logger.exception("tool %s raised", call["name"])
        return ToolMessage(
            content=(
                f"{call['name']} failed ({type(problem).__name__}: {str(problem)[:300]}). Check its arguments "
                "and the current project context before trying again."
            ),
            tool_call_id=call["id"],
            name=call["name"],
            status="error",
        )

    def _invalid(self, call: dict, problem: Exception) -> None:
        """Bad arguments keep LangChain's "fix the arguments" answer, but count as a failure and are logged."""
        from langgraph.prebuilt.tool_node import ToolInvocationError

        if isinstance(problem, ToolInvocationError):
            logger.warning(
                "tool %s got invalid arguments: %s", call["name"], str(problem)[:500]
            )
            self._failed_calls.add(self._key(call))
            self._failures[call["name"]] = self._failures.get(call["name"], 0) + 1

    @staticmethod
    def _passes_through(problem: Exception) -> bool:
        """Pauses for the user and bad arguments keep their own handling."""
        from langgraph.errors import GraphBubbleUp
        from langgraph.prebuilt.tool_node import ToolInvocationError

        return isinstance(problem, (GraphBubbleUp, ToolInvocationError))

    def wrap_tool_call(self, request, handler):
        blocked = self._blocked(request.tool_call)
        if blocked is not None:
            return blocked
        try:
            result = handler(request)
        except Exception as problem:
            if self._passes_through(problem):
                self._invalid(request.tool_call, problem)
                raise
            result = self._crashed(request.tool_call, problem)
        self._record(request.tool_call, result)
        return result

    async def awrap_tool_call(self, request, handler):
        blocked = self._blocked(request.tool_call)
        if blocked is not None:
            return blocked
        try:
            result = await handler(request)
        except Exception as problem:
            if self._passes_through(problem):
                self._invalid(request.tool_call, problem)
                raise
            result = self._crashed(request.tool_call, problem)
        self._record(request.tool_call, result)
        return result


def breakers() -> list[AgentMiddleware]:
    """Fresh per-run limits, outermost first. Each agent and specialist needs its own instances."""
    return [
        TurnLimit(run_limit=setting("AGENT_MAX_MODEL_CALLS", 50), exit_behavior="end"),
        ToolCallLimitMiddleware(
            run_limit=setting("AGENT_MAX_TOOL_CALLS", 50), exit_behavior="continue"
        ),
        RepeatFailureBreaker(setting("AGENT_MAX_TOOL_FAILURES", 3)),
    ]


def transient(problem: BaseException) -> bool:
    """Connection, timeout, rate-limit and server errors are worth retrying; credentials and bad requests are not."""
    status = getattr(problem, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    return type(problem).__name__ in {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ReadTimeout",
        "TimeoutError",
    }


def resilience(fallback_model=None) -> list[AgentMiddleware]:
    """Keep a turn alive through provider hiccups. After the retries the error is raised again, so the chat still
    says what went wrong."""
    stack: list[AgentMiddleware] = [
        ModelRetryMiddleware(
            max_retries=setting("AGENT_MODEL_RETRIES", 2),
            retry_on=transient,
            on_failure="error",
            initial_delay=2.0,
        )
    ]
    if fallback_model is not None:
        stack.append(ModelFallbackMiddleware(fallback_model))
    return stack


def _text(message: Any) -> str:
    content = message.content
    if not isinstance(content, str):
        content = " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return " ".join(content.split())


def conversation_digest(messages: list) -> str:
    """When no model summary came back: what the user and wizi said and which tools ran, newest kept first within
    DIGEST_CHARS, so a compaction never leaves wizi with nothing."""
    lines = []
    for message in messages:
        if from_harness(message):
            continue
        kind = getattr(message, "type", "")
        text = _text(message)
        if kind == "human" and text:
            lines.append(f"User: {text[:600]}")
        elif kind == "ai":
            if text:
                lines.append(f"wizi: {text[:600]}")
            tools = ", ".join(
                call["name"] for call in getattr(message, "tool_calls", None) or []
            )
            if tools:
                lines.append(f"(wizi used: {tools})")
    kept, used = [], 0
    for line in reversed(lines):
        if used + len(line) > DIGEST_CHARS:
            break
        kept.append(line)
        used += len(line) + 1
    return (
        "No model summary was available; this digest lists the earlier exchange (oldest first; tool results "
        "are in the conversation history file):\n" + "\n".join(reversed(kept))
    )


def checked_summary(folded: list, summary: str) -> str:
    """The summary, or the digest when the summarizer returned one of its empty placeholders."""
    if summary.strip() in EMPTY_SUMMARIES and folded:
        logger.error(
            "compaction: the summarizer returned %r for %s messages; a digest replaces it",
            summary,
            len(folded),
        )
        return conversation_digest(folded)
    logger.info("compaction: folded %s messages", len(folded))
    return summary
