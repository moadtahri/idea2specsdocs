"""Inspect recent checkpoint errors using disposable copies of project databases."""

import asyncio
import sqlite3
import tempfile
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app import store


async def inspect():
    for project in store.list_projects()[:4]:
        source = store.checkpoint_path(project.project_id)
        if not source.exists():
            continue
        print("Project:", project.project_id, flush=True)
        attachments = store._connect()
        rows = attachments.execute(
            "SELECT filename, size, length(text_preview) FROM attachments WHERE project_id = ?",
            (project.project_id,),
        ).fetchall()
        attachments.close()
        print("Attachments:", [tuple(row) for row in rows], flush=True)
        with tempfile.TemporaryDirectory(prefix="idea2spec-inspect-") as temporary:
            destination = Path(temporary) / "checkpoint.db"
            with (
                sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as live,
                sqlite3.connect(destination) as backup,
            ):
                live.backup(backup)
            async with AsyncSqliteSaver.from_conn_string(str(destination)) as saver:
                async for checkpoint in saver.alist(
                    {"configurable": {"thread_id": project.thread_id}}, limit=3
                ):
                    print("Checkpoint:", checkpoint.metadata.get("step"), flush=True)
                    for _task, channel, value in checkpoint.pending_writes or []:
                        if channel == "__error__":
                            print("Failure:", str(value)[:1800], flush=True)
                    messages = checkpoint.checkpoint.get("channel_values", {}).get(
                        "messages", []
                    )
                    print(
                        "Recent message types:",
                        [
                            getattr(message, "type", "unknown")
                            for message in messages[-8:]
                        ],
                        flush=True,
                    )


if __name__ == "__main__":
    asyncio.run(inspect())
