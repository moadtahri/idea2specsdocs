import asyncio
import io
import zipfile
from typing import ClassVar

from langchain.messages import AIMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult

from app import source_context, store
from app.agent import factory
from app.agent.factory import scoped_env


def source_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return buffer.getvalue()


SOURCE = {
    "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    "tests/test_main.py": "def test_ok():\n    assert True\n",
    "node_modules/x/index.js": "skipped",
    ".env": "SECRET=1",
    "../evil.py": "outside",
    "logo.png": "binary-ish",
}


def test_source_files_keep_the_snapshot_filters():
    files, skipped = source_context.source_files(source_zip(SOURCE))
    assert sorted(files) == ["app/main.py", "tests/test_main.py"]
    assert skipped == 4
    snapshot = source_context.source_archive_context(source_zip(SOURCE))
    assert snapshot.startswith("Source snapshot: 2 files included; 4 files skipped.")
    assert '--- Source file: "app/main.py" ---' in snapshot


def test_the_tree_stays_inside_its_folder(tmp_path):
    index = source_context.write_source_tree(
        tmp_path, {"app/main.py": "a\nb\n", "../../escape.py": "x", "/abs.py": "y"}
    )
    assert (tmp_path / "source" / "app" / "main.py").read_text() == "a\nb\n"
    assert not (tmp_path.parent / "escape.py").exists()
    assert not (tmp_path / "abs.py").exists()
    assert "| `app/main.py` | 2 |" in index.read_text()
    assert "escape" not in index.read_text()


def test_a_source_upload_gets_a_tree_and_wizi_is_told_where(client, project):
    response = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("repo.zip", source_zip(SOURCE), "application/zip")},
    )
    assert response.status_code == 201
    attachment = response.json()["attachment_id"]
    folder = store.PROJECTS_DIR / project / "uploads" / attachment
    assert (folder / "source" / "app" / "main.py").is_file()
    assert (folder / "source-index.md").is_file()
    assert not (folder / "source" / ".env").exists()


def test_wizi_is_pointed_at_the_tree_not_the_snapshot(client, project, monkeypatch):
    from app import main

    seen = []

    class Agent:
        async def aget_state(self, config):
            from types import SimpleNamespace

            return SimpleNamespace(interrupts=())

        async def astream(self, value, **kwargs):
            seen.append(value["messages"][0]["content"])
            return
            yield

    class Saver:
        async def __aexit__(self, *args):
            return None

    async def build(*args):
        return Agent(), Saver()

    monkeypatch.setattr(main, "build_agent", build)
    upload = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("repo.zip", source_zip(SOURCE), "application/zip")},
    ).json()
    with client.stream(
        "POST",
        "/api/chat",
        json={
            "project_id": project,
            "message": "Read my code",
            "attachment_ids": [upload["attachment_id"]],
        },
    ) as response:
        list(response.iter_lines())
    [message] = seen
    assert f"/uploads/{upload['attachment_id']}/source/" in message
    assert ".context.txt" not in message


def test_the_reader_has_no_register_tools_and_cannot_write():
    spec = factory.repo_reader()
    assert spec["name"] == "repo-reader" and spec["tools"] == []
    [rule] = spec["permissions"]
    assert rule.operations == ["write"] and rule.mode == "deny"
    assert spec["interrupt_on"] == {}


class Scripted(BaseChatModel):
    replies: ClassVar[list[AIMessage]] = []
    tools_seen: ClassVar[list[list[str]]] = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        Scripted.tools_seen.append(
            [tool.name if hasattr(tool, "name") else tool["name"] for tool in tools]
        )
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=Scripted.replies.pop(0))])


def test_wizi_delegates_and_the_reader_reads_but_never_writes(
    client, project, monkeypatch
):
    directory = store.PROJECTS_DIR / project
    source_context.write_source_tree(
        directory / "uploads" / "a1", {"app/main.py": "app = 1\n"}
    )

    def calls(*pairs):
        return AIMessage(
            content="",
            tool_calls=[
                {"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(pairs)
            ],
        )

    Scripted.replies[:] = [
        calls(
            (
                "task",
                {
                    "subagent_type": "repo-reader",
                    "description": "Where does the app start? /uploads/a1/source/",
                },
            )
        ),
        calls(("write_file", {"file_path": "/docs/prd.md", "content": "hijacked"})),
        calls(("read_file", {"file_path": "/uploads/a1/source/app/main.py"})),
        AIMessage(content="1. Stack: Python (app/main.py:1)"),
        AIMessage(content="The app starts in app/main.py."),
    ]
    Scripted.tools_seen.clear()
    monkeypatch.setattr(factory, "build_llm", Scripted)

    async def run():
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                return await graph.ainvoke(
                    {"messages": [("user", "Read my repo")]},
                    {"configurable": {"thread_id": project}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    state = asyncio.run(run())
    assert "__interrupt__" not in state  # a denied write asks the user nothing
    assert not (directory / "docs" / "prd.md").exists()
    [report] = [
        m for m in state["messages"] if isinstance(m, ToolMessage) and m.name == "task"
    ]
    assert "app/main.py:1" in report.content
    assert state["messages"][-1].content == "The app starts in app/main.py."
    reader_tools = [
        names
        for names in Scripted.tools_seen
        if "propose_work_item" not in names and "task" not in names
    ]
    assert reader_tools and "settle_decision" not in reader_tools[0]


def test_every_write_asks_and_only_documents_and_specs_are_written(
    client, project, monkeypatch
):
    from langgraph.types import Command

    from app.quality_models import BRIEF_FIELDS

    state = client.put(
        f"/api/projects/{project}/brief",
        json={f: f"Confirmed {f}" for f in BRIEF_FIELDS},
    ).json()
    client.post(
        f"/api/projects/{project}/brief/approve", json={"revision": state["revision"]}
    )
    directory = store.PROJECTS_DIR / project

    def write(*paths):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_file",
                    "args": {"file_path": path, "content": "x"},
                    "id": f"w{i}",
                }
                for i, path in enumerate(paths)
            ],
        )

    # Dot folders are named apart: `**` alone skipped `/.ai/…`, which then saved with no card at all.
    paths = [
        "/tmp/test-tool.md",
        "/.ai/specs/01-x.md",
        "/docs/prd.md",
        "/specs/README.md",
    ]
    Scripted.replies[:] = [write(*paths), AIMessage(content="done")]
    monkeypatch.setattr(factory, "build_llm", Scripted)
    config = {"configurable": {"thread_id": project}}

    async def run():
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                paused = await graph.ainvoke({"messages": [("user", "Draft")]}, config)
                approved = await graph.ainvoke(
                    Command(resume={"decisions": [{"type": "approve"}] * 4}), config
                )
                return paused, approved
            finally:
                await manager.__aexit__(None, None, None)

    paused, approved = asyncio.run(run())
    [card] = paused["__interrupt__"]  # nothing is written without the user's approval
    assert [a["args"]["file_path"] for a in card.value["action_requests"]] == paths
    results = {
        m.tool_call_id: m.status
        for m in approved["messages"]
        if isinstance(m, ToolMessage)
    }
    assert results == {"w0": "error", "w1": "error", "w2": "success", "w3": "success"}
    assert not (directory / "tmp").exists() and not (directory / ".ai").exists()
    assert (directory / "docs" / "prd.md").is_file() and (
        directory / "specs" / "README.md"
    ).is_file()
