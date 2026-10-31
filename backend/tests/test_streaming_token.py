import httpx
import pytest

from app import main

from .test_progress_and_transcription import install_assemblyai_transport


def test_streaming_token_uses_server_key_and_disables_caching(client, monkeypatch):
    permanent = "server-only-assemblyai-key"
    monkeypatch.setattr(main, "resolve_assemblyai_api_key", lambda: permanent)

    def handler(request):
        assert str(request.url).startswith("https://streaming.assemblyai.com/v3/token")
        assert request.headers["authorization"] == permanent
        assert request.url.params["expires_in_seconds"] == "60"
        assert request.url.params["max_session_duration_seconds"] == "360"
        return httpx.Response(200, json={"token": "temporary-browser-token"})

    install_assemblyai_transport(monkeypatch, handler)
    response = client.post("/api/transcribe/token")
    assert response.status_code == 200
    assert response.json() == {
        "token": "temporary-browser-token",
        "websocket_url": "wss://streaming.assemblyai.com/v3/ws",
        "sample_rate": 16000,
    }
    assert response.headers["cache-control"] == "no-store"
    assert permanent not in response.text


def test_streaming_missing_key_is_actionable(client, monkeypatch):
    monkeypatch.setattr(main, "resolve_assemblyai_api_key", lambda: None)
    response = client.post("/api/transcribe/token")
    assert response.status_code == 503
    assert "voice note" in response.json()["detail"]


@pytest.mark.parametrize(
    "status,payload",
    [
        (401, {"error": "server-only-assemblyai-key"}),
        (429, {"error": "quota"}),
        (500, {}),
        (200, {}),
        (200, {"token": "server-only-assemblyai-key"}),
        (200, {"token": ""}),
        (200, []),
    ],
)
def test_streaming_failures_never_expose_permanent_key(
    client, monkeypatch, status, payload
):
    monkeypatch.setattr(
        main, "resolve_assemblyai_api_key", lambda: "server-only-assemblyai-key"
    )
    install_assemblyai_transport(
        monkeypatch, lambda _: httpx.Response(status, json=payload)
    )
    response = client.post("/api/transcribe/token")
    assert response.status_code == 502
    assert "server-only-assemblyai-key" not in response.text
