"""Talk to a running itos server the way the browser does, and read what the chat stream does not show.

The SSE stream carries tool names but not their arguments, so graders read wizi's full tool calls from the
project's checkpoint after each turn. That needs the server's project folder on this host (``store.PROJECTS_DIR``).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import httpx

from app import store


@dataclass
class Turn:
    """One chat request and what came back."""

    text: str = ""
    tools: list[str] = field(default_factory=list)
    # One entry per action awaiting approval: {"name": tool, "path": file_path or ""}.
    interrupts: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "text": self.text,
            "tools": self.tools,
            "interrupts": self.interrupts,
            "errors": self.errors,
        }


def chat(
    client: httpx.Client,
    project: str,
    message: str = "",
    *,
    resume: list | None = None,
    attachment_ids: tuple[str, ...] = (),
) -> Turn:
    body: dict = {"project_id": project}
    if resume is not None:
        body["resume"] = resume
    else:
        body["message"] = message
        body["attachment_ids"] = list(attachment_ids)
    turn = Turn()
    text = []
    with client.stream("POST", "/api/chat", json=body, timeout=900) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            event = json.loads(line[5:])
            kind = event.get("type")
            if kind == "token":
                text.append(event.get("text", ""))
            elif kind == "tool_call" and event.get("source") == "main":
                turn.tools.append(event.get("name", ""))
            elif kind == "interrupt":
                turn.interrupts += [
                    {
                        "name": action.get("name", ""),
                        "path": str(action.get("args", {}).get("file_path", "")),
                    }
                    for action in event.get("action_requests", [])
                ]
            elif kind == "error":
                turn.errors.append(event.get("detail", ""))
    turn.text = "".join(text)
    return turn


def approve(client: httpx.Client, project: str, waiting: Turn) -> Turn:
    """Approve every action the last turn paused on, as the card's Approve & save does."""
    return chat(
        client, project, resume=[{"type": "approve"} for _ in waiting.interrupts]
    )


def main_calls(project: str) -> list[dict]:
    """Every tool call wizi itself made in this project's thread, oldest first: ``{"name", "args"}``."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    record = store.get_project(project)
    if record is None:
        return []

    async def read() -> list[dict]:
        # This langgraph keeps message updates as writes on each checkpoint, not as a stored channel value, so the
        # calls are gathered from every write to "messages" (main graph only: checkpoint_ns ""), oldest first.
        calls: dict[str, dict] = {}
        async with AsyncSqliteSaver.from_conn_string(
            str(store.checkpoint_path(project))
        ) as saver:
            saved = [
                t
                async for t in saver.alist(
                    {
                        "configurable": {
                            "thread_id": record.thread_id,
                            "checkpoint_ns": "",
                        }
                    }
                )
            ]
        for checkpoint in reversed(saved):
            stored = (
                checkpoint.checkpoint.get("channel_values", {}).get("messages") or []
            )
            written = [
                value
                for _task, channel, value in (checkpoint.pending_writes or [])
                if channel == "messages"
            ]
            for value in [stored, *written]:
                for message in value if isinstance(value, list) else [value]:
                    for call in getattr(message, "tool_calls", None) or []:
                        calls.setdefault(
                            call.get("id") or str(len(calls)),
                            {
                                "name": call.get("name", ""),
                                "args": call.get("args", {}),
                            },
                        )
        return list(calls.values())

    return asyncio.run(read())


def quality(client: httpx.Client, project: str) -> dict:
    response = client.get(f"/api/projects/{project}/quality")
    response.raise_for_status()
    return response.json()
