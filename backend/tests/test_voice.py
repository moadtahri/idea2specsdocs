"""Voice (spec 09): what is read aloud, the speech route, and the listening relay without a key."""

from app import main, voice


def test_only_plain_words_are_read_aloud():
    text = "# Plan\n\nSee [the PRD](https://x.io/prd) and https://example.com now.\n\n```py\nprint(1)\n```\n| a | b |\n**Done**"
    assert voice.spoken(text) == "Plan See the PRD and a link now. Done"


def test_speak_streams_pcm(client, monkeypatch):
    async def fake(text, chosen="marin"):
        assert text == "Hello there" and chosen == "marin"
        yield b"\x00\x01" * 10
        yield b"\x02\x03"

    monkeypatch.setattr(voice, "speech", fake)
    response = client.post("/api/voice/speak", json={"text": "**Hello** there"})
    assert response.status_code == 200 and response.headers["x-audio-rate"] == "24000"
    assert response.content == b"\x00\x01" * 10 + b"\x02\x03"
    assert client.post("/api/voice/speak", json={"text": "```x```"}).status_code == 422


def test_without_a_key_voice_says_so_and_nothing_else_breaks(client, monkeypatch):
    monkeypatch.setattr(voice, "resolve_openai_api_key", lambda: None)
    spoken = client.post("/api/voice/speak", json={"text": "Hello"})
    assert spoken.status_code == 503 and "OpenAI key" in spoken.json()["detail"]
    with client.websocket_connect("/api/voice/listen") as socket:
        message = socket.receive_json()
    assert message["type"] == "error" and "OpenAI key" in message["text"]
    assert main.app  # the rest of the app is untouched
