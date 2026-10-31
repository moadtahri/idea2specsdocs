import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest
from langchain.messages import AIMessageChunk

from app import main, secrets, store
from app.agent import bundles
from app.schemas import DOC_SLUGS
from app.source_context import source_archive_context


def secret_result(value, key="ASSEMBLYAI_API_KEY"):
    return {"status": 200, "error": {}, "data": {"message": {key: value}}}


def write_doc(project, body="# Scope\n\nFR-1: Add saved searches."):
    path = store.PROJECTS_DIR / project / "docs" / "prd.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_transcription_fetches_named_aws_key_and_preserves_audio_type(
    client, monkeypatch
):
    monkeypatch.setenv("ASSEMBLYAI_SECRET_NAME", "voice-secrets")
    monkeypatch.delenv("ASSEMBLYAI_SECRET_KEY", raising=False)
    manager = MagicMock()
    manager.get_secrets.return_value = secret_result("test-credential")
    monkeypatch.setattr(secrets, "AwsSecretManager", lambda: manager)
    transcription = AsyncMock(return_value="Add saved searches")
    monkeypatch.setattr(main, "transcribe_audio", transcription)

    response = client.post(
        "/api/transcribe", files={"file": ("voice.mp4", b"audio", "audio/mp4")}
    )
    assert response.status_code == 200
    assert response.json() == {"text": "Add saved searches"}
    manager.get_secrets.assert_called_once_with("voice-secrets")
    transcription.assert_awaited_once_with(b"audio", "test-credential")


@pytest.mark.parametrize(
    "value",
    [None, "", "  ", 123, {"status": -1, "error": {"message": "private detail"}}],
)
def test_missing_aws_key_does_not_fall_back_to_env(client, monkeypatch, value):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "must-not-be-used")
    manager = MagicMock()
    manager.get_secrets.return_value = secret_result(value)
    monkeypatch.setattr(secrets, "AwsSecretManager", lambda: manager)
    response = client.post(
        "/api/transcribe", files={"file": ("voice.webm", b"audio", "audio/webm")}
    )
    assert response.status_code == 503
    assert "AWS" in response.json()["detail"]
    assert "private detail" not in response.text
    assert "must-not-be-used" not in response.text


def test_secret_lookup_retries_and_falls_back_to_model_secret(monkeypatch):
    monkeypatch.delenv("ASSEMBLYAI_SECRET_NAME", raising=False)
    monkeypatch.delenv("ASSEMBLYAI_SECRET_KEY", raising=False)
    monkeypatch.setenv("MODEL_SECRET_NAME", "shared-secret")
    manager = MagicMock()
    manager.get_secrets.side_effect = [
        {"status": -1, "error": {"message": "temporary"}},
        secret_result("test-credential"),
    ]
    monkeypatch.setattr(secrets, "AwsSecretManager", lambda: manager)
    assert secrets.resolve_assemblyai_api_key() is None
    assert secrets.resolve_assemblyai_api_key() == "test-credential"
    assert manager.get_secrets.call_count == 2
    manager.get_secrets.assert_called_with("shared-secret")


def test_empty_and_oversized_recordings_do_not_fetch_secrets(client, monkeypatch):
    resolver = MagicMock()
    monkeypatch.setattr(main, "resolve_assemblyai_api_key", resolver)
    monkeypatch.setattr(main, "MAX_UPLOAD_BYTES", 8)
    for payload, status in [(b"", 400), (b"x" * 9, 413)]:
        assert (
            client.post(
                "/api/transcribe", files={"file": ("voice.webm", payload, "audio/webm")}
            ).status_code
            == status
        )
    resolver.assert_not_called()


def test_provider_errors_are_readable_and_do_not_leak_credentials(client, monkeypatch):
    monkeypatch.setattr(main, "resolve_assemblyai_api_key", lambda: "test-credential")
    monkeypatch.setattr(
        main,
        "transcribe_audio",
        AsyncMock(side_effect=RuntimeError("test-credential private backend detail")),
    )
    response = client.post(
        "/api/transcribe", files={"file": ("voice.webm", b"audio", "audio/webm")}
    )
    assert response.status_code == 502
    assert "test-credential" not in response.text
    assert "retry" in response.json()["detail"]


def test_both_bundles_download_and_readable_cache_refreshes(
    client, project, monkeypatch
):
    path = write_doc(project)
    invoke = AsyncMock(
        return_value=SimpleNamespace(
            content="## What changes\n\nUsers can save searches (FR-1)."
        )
    )
    monkeypatch.setattr(bundles, "build_llm", lambda: SimpleNamespace(ainvoke=invoke))
    url = f"/api/projects/{project}/docs"
    agent = client.get(f"{url}/bundle-agent/download")
    assert agent.status_code == 200
    assert "status: missing" in agent.text
    assert "FR-1" in agent.text
    for slug in DOC_SLUGS:
        assert f"<!-- BEGIN DOC slug={slug} -->" in agent.text
    readable = client.get(f"{url}/bundle")
    assert readable.status_code == 200
    assert "Users can save searches" in readable.json()["markdown"]
    download = client.get(f"{url}/bundle/download")
    assert download.text == readable.json()["markdown"]
    assert 'filename="bundle.md"' in download.headers["content-disposition"]
    assert invoke.await_count == 1
    path.write_text("FR-2: Share saved searches", encoding="utf-8")
    assert client.get(f"{url}/bundle").status_code == 200
    assert invoke.await_count == 2


def test_empty_bundles_and_readable_failures(client, project, monkeypatch):
    url = f"/api/projects/{project}/docs"
    for slug in ("bundle", "bundle-agent"):
        assert client.get(f"{url}/{slug}").status_code == 404
    write_doc(project)
    monkeypatch.setattr(
        bundles, "build_llm", MagicMock(side_effect=RuntimeError("private"))
    )
    response = client.get(f"{url}/bundle")
    assert response.status_code == 503
    assert "private" not in response.text
    assert client.get(f"{url}/bundle-agent").status_code == 200


def test_source_upload_full_context_survives_preview_limit(client, project):
    source = "# Existing source\n" + "x = 1\n" * 1200 + "# end of source"
    response = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("feature.py", source, "application/octet-stream")},
    )
    assert response.status_code == 201
    attachment = response.json()
    assert "Preview truncated" in attachment["text_preview"]
    full = (
        store.PROJECTS_DIR
        / project
        / "uploads"
        / f"{attachment['attachment_id']}.context.txt"
    )
    assert full.read_text(encoding="utf-8") == source


def archive(files):
    output = io.BytesIO()
    with ZipFile(output, "w") as zipped:
        for name, data in files.items():
            zipped.writestr(name, data)
    return output.getvalue()


def test_archive_context_includes_source_and_excludes_unsafe_or_generated_paths():
    result = source_archive_context(
        archive(
            {
                "src/app.ts": "const ready = true;",
                "docs/prd.md": "FR-1: Existing behavior",
                "../escape.py": "unsafe path",
                "node_modules/library/index.js": "dependency",
                ".env": "credential",
                "binary.py": b"\x00\xff",
            }
        )
    )
    assert "2 files included; 4 files skipped" in result
    assert "FR-1" in result
    assert "const ready" in result
    assert "unsafe path" not in result
    assert "credential" not in result


def test_archive_rejects_invalid_and_expanded_oversize(monkeypatch):
    with pytest.raises(ValueError, match="valid ZIP"):
        source_archive_context(b"not a zip")
    monkeypatch.setattr("app.source_context.MAX_EXPANDED_BYTES", 10)
    with pytest.raises(ValueError, match="too large"):
        source_archive_context(archive({"source.py": "x" * 11}))


def test_chat_emits_text_only_and_resumes_approval(client, project, monkeypatch):
    inputs = []

    class Agent:
        async def aget_state(self, config):
            return SimpleNamespace(interrupts=())  # no card waits

        async def astream(self, value, **kwargs):
            inputs.append(value)
            yield (
                (),
                "messages",
                (
                    AIMessageChunk(
                        content=[
                            {"type": "text", "text": "Please review this draft."},
                            {"type": "reasoning", "reasoning": "internal"},
                        ]
                    ),
                    {},
                ),
            )
            yield (
                ("tools:specialist",),
                "messages",
                (AIMessageChunk(content="private specialist notes"), {}),
            )
            if len(inputs) == 1:
                yield (
                    (),
                    "updates",
                    {
                        "__interrupt__": [
                            SimpleNamespace(
                                id="review-1",
                                value={
                                    "action_requests": [
                                        {
                                            "name": "write_file",
                                            "args": {
                                                "file_path": "/docs/prd.md",
                                                "content": "FR-1",
                                            },
                                        }
                                    ],
                                    "review_configs": [],
                                },
                            )
                        ]
                    },
                )

    closer = SimpleNamespace(__aexit__=AsyncMock())

    async def build(*args):
        return Agent(), closer

    monkeypatch.setattr(main, "build_agent", build)
    first = client.post(
        "/api/chat", json={"project_id": project, "message": "Draft it"}
    )
    events = [
        json.loads(line[5:])
        for line in first.text.splitlines()
        if line.startswith("data:")
    ]
    assert any(event["type"] == "interrupt" for event in events)
    assert "internal" not in first.text
    assert "private specialist" not in first.text
    assert [event["text"] for event in events if event["type"] == "token"] == [
        "Please review this draft."
    ]
    resumed = client.post(
        "/api/chat", json={"project_id": project, "resume": [{"type": "approve"}]}
    )
    assert resumed.status_code == 200
    assert inputs[1].resume["decisions"][0]["type"] == "approve"
    assert closer.__aexit__.await_count == 2
