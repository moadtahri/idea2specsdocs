"""Voice for the chat, as in Kanya's (spec 09, ported from Canyas ``canyas_api/routers/voice.py``).

- ``relay(socket)`` serves ``WS /api/voice/listen``: the browser sends raw 16-bit 24 kHz mono PCM; it goes to an
  OpenAI realtime **transcription** session (server-side turn detection), and the page gets back
  ``{"type": "partial", "text"}`` while you speak, ``{"type": "final", "text"}`` when a sentence ends, and
  ``{"type": "speech_started"}`` (the page stops wizi's voice when you talk over it).
- ``speech(text)`` serves ``POST /api/voice/speak``: wizi's reply in, its voice out as a stream of the same PCM
  (streaming text to speech, the first audio in about a second). Markdown and links are dropped from what is read.

The OpenAI key comes from AWS Secrets Manager (``secrets.resolve_openai_api_key``) and never reaches the browser.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .secrets import resolve_openai_api_key

logger = logging.getLogger("itos.voice")
RATE = 24000
MAX_SPEAK_CHARS = 2400
MAX_LISTEN_SECONDS = 600
TRANSCRIBE_MODEL = os.environ.get("VOICE_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
SPEAK_MODEL = os.environ.get("VOICE_SPEAK_MODEL", "gpt-4o-mini-tts")
SPEAK_STYLE = "Warm, clear and unhurried, like a helpful colleague; natural pauses; no announcer voice."


class VoiceUnavailable(RuntimeError):
    """No OpenAI key could be read: voice is off, the rest of the app works."""


def _api_key() -> str:
    key = resolve_openai_api_key()
    if not key:
        raise VoiceUnavailable("Voice needs the OpenAI key in AWS Secrets Manager.")
    return key


def spoken(text: str) -> str:
    """What wizi says aloud: the reply without markdown, links, code or tables."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"https?://\S+", "a link", text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_SPEAK_CHARS]


async def speech(text: str, voice: str = "marin") -> AsyncIterator[bytes]:
    """Streaming speech as 24 kHz 16-bit mono PCM."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=_api_key(), timeout=120.0, max_retries=1)
    async with client.audio.speech.with_streaming_response.create(
        model=SPEAK_MODEL,
        voice=voice,
        input=text,
        instructions=SPEAK_STYLE,
        response_format="pcm",
    ) as response:
        async for chunk in response.iter_bytes(4800):
            yield chunk


async def relay(socket: WebSocket) -> None:
    """Relay the microphone to OpenAI realtime transcription and the words back to the page."""
    await socket.accept()
    from openai import AsyncOpenAI

    try:
        client = AsyncOpenAI(api_key=_api_key(), timeout=60.0, max_retries=1)
        async with client.realtime.connect(
            extra_query={"intent": "transcription"}
        ) as upstream:
            transcription: Any = {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": RATE},
                        "transcription": {"model": TRANSCRIBE_MODEL, "language": "en"},
                        "turn_detection": {
                            "type": "server_vad",
                            "silence_duration_ms": 700,
                        },
                        "noise_reduction": {"type": "near_field"},
                    }
                },
            }
            await upstream.session.update(session=transcription)
            await socket.send_text(json.dumps({"type": "ready"}))

            async def browser_to_openai() -> None:
                started = asyncio.get_event_loop().time()
                while True:
                    message = await socket.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    chunk = message.get("bytes")
                    if chunk:
                        await upstream.input_audio_buffer.append(
                            audio=base64.b64encode(chunk).decode()
                        )
                    elif (
                        message.get("text")
                        and json.loads(message["text"]).get("type") == "stop"
                    ):
                        # Turn detection already ended the sentence; wait for its transcript to come back.
                        await asyncio.sleep(1.5)
                        return
                    if asyncio.get_event_loop().time() - started > MAX_LISTEN_SECONDS:
                        return

            async def openai_to_browser() -> None:
                partial: dict[str, str] = {}
                async for raw in upstream:
                    event: Any = raw
                    kind = event.type
                    if kind == "conversation.item.input_audio_transcription.delta":
                        item = getattr(event, "item_id", "")
                        partial[item] = partial.get(item, "") + (event.delta or "")
                        await socket.send_text(
                            json.dumps({"type": "partial", "text": partial[item]})
                        )
                    elif (
                        kind == "conversation.item.input_audio_transcription.completed"
                    ):
                        partial.pop(getattr(event, "item_id", ""), None)
                        await socket.send_text(
                            json.dumps(
                                {
                                    "type": "final",
                                    "text": (event.transcript or "").strip(),
                                }
                            )
                        )
                    elif kind == "input_audio_buffer.speech_started":
                        await socket.send_text(json.dumps({"type": "speech_started"}))
                    elif kind == "error":
                        await socket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "text": "Voice is not available right now.",
                                }
                            )
                        )
                        logger.warning(
                            "realtime transcription error: %s",
                            getattr(event, "error", event),
                        )

            sender = asyncio.create_task(browser_to_openai())
            receiver = asyncio.create_task(openai_to_browser())
            await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            for task in (sender, receiver):
                task.cancel()
    except WebSocketDisconnect:
        return
    except VoiceUnavailable as problem:
        with contextlib.suppress(Exception):
            await socket.send_text(json.dumps({"type": "error", "text": str(problem)}))
    except Exception:  # the page hears a plain error; the log keeps the cause
        logger.exception("voice listening failed")
        with contextlib.suppress(Exception):
            await socket.send_text(
                json.dumps(
                    {"type": "error", "text": "Voice is not available right now."}
                )
            )
    with contextlib.suppress(Exception):
        await socket.close()
