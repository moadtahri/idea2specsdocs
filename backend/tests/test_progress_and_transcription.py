import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app import main, transcription
from app.agent.factory import scoped_env
from app.agent.tools import PROJECT_DIRECTORY
from app.schemas import ChatRequest

HTTP_CLIENT = httpx.AsyncClient


def test_progress_is_yielded_before_agent_setup(monkeypatch, tmp_path):
    project = SimpleNamespace(thread_id="thread")
    monkeypatch.setattr(main, "_require_project", lambda _: project)
    monkeypatch.setattr(main, "_project_dir", lambda _: tmp_path)
    monkeypatch.setattr(main.store, "checkpoint_path", lambda _: tmp_path / "state.db")
    build = AsyncMock()
    monkeypatch.setattr(main, "build_agent", build)

    async def check():
        response = await main.chat(
            ChatRequest(project_id="project", message="Plan a todo app")
        )
        iterator = response.body_iterator
        first = json.loads(await anext(iterator))
        assert first["type"] == "status"
        assert "Connecting" in first["text"]
        build.assert_not_awaited()
        await iterator.aclose()

    asyncio.run(check())


def test_concurrent_projects_keep_their_own_tool_directory(tmp_path):
    async def run(path):
        with scoped_env(path):
            await asyncio.sleep(0)
            assert PROJECT_DIRECTORY.get() == path

    async def check():
        await asyncio.gather(run(tmp_path / "first"), run(tmp_path / "second"))
        assert PROJECT_DIRECTORY.get() is None

    asyncio.run(check())


def install_assemblyai_transport(monkeypatch, handler):
    monkeypatch.setattr(
        transcription.httpx,
        "AsyncClient",
        lambda **kwargs: HTTP_CLIENT(
            **kwargs,
            transport=httpx.MockTransport(handler),
        ),
    )
    monkeypatch.setattr(transcription, "POLL_INTERVAL", 0)


def test_assemblyai_uploads_bytes_and_polls_until_completed(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["authorization"] == "test-assemblyai-key"
        if request.url.path == "/v2/upload":
            assert request.content == b"audio bytes"
            assert request.headers["content-type"] == "application/octet-stream"
            return httpx.Response(
                200, json={"upload_url": "https://cdn.assemblyai.com/upload/test"}
            )
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["audio_url"].endswith("/test")
            return httpx.Response(200, json={"id": "job", "status": "queued"})
        return httpx.Response(
            200, json={"id": "job", "status": "completed", "text": "Create a todo app"}
        )

    install_assemblyai_transport(monkeypatch, handler)
    assert (
        asyncio.run(
            transcription.transcribe_audio(b"audio bytes", "test-assemblyai-key")
        )
        == "Create a todo app"
    )
    assert [request.method for request in requests] == ["POST", "POST", "GET"]


@pytest.mark.parametrize(
    "status, expected",
    [(401, "rejected"), (403, "rejected"), (429, "quota"), (500, "retry")],
)
def test_assemblyai_provider_errors_are_readable(monkeypatch, status, expected):
    install_assemblyai_transport(
        monkeypatch,
        lambda _: httpx.Response(status, json={"error": "private test-assemblyai-key"}),
    )
    with pytest.raises(transcription.TranscriptionError, match=expected) as failure:
        asyncio.run(transcription.transcribe_audio(b"audio", "test-assemblyai-key"))
    assert "test-assemblyai-key" not in str(failure.value)


def test_assemblyai_job_failure_and_timeout(monkeypatch):
    def handler(request):
        if request.url.path == "/v2/upload":
            return httpx.Response(
                200, json={"upload_url": "https://cdn.assemblyai.com/upload/test"}
            )
        return httpx.Response(
            200, json={"id": "job", "status": "error", "error": "private"}
        )

    install_assemblyai_transport(monkeypatch, handler)
    with pytest.raises(transcription.TranscriptionError, match="record again"):
        asyncio.run(transcription.transcribe_audio(b"audio", "key"))
    monkeypatch.setattr(transcription, "TRANSCRIPTION_TIMEOUT", 0)

    async def slow_handler(_request):
        await asyncio.sleep(0.01)
        return httpx.Response(200, json={})

    install_assemblyai_transport(monkeypatch, slow_handler)
    with pytest.raises(transcription.TranscriptionError, match="too long"):
        asyncio.run(transcription.transcribe_audio(b"audio", "key"))
