"""Asynchronous AssemblyAI upload, submission and bounded polling."""

import asyncio
import time

import httpx

BASE_URL = "https://api.assemblyai.com/v2"
POLL_INTERVAL = 2
TRANSCRIPTION_TIMEOUT = 120
STREAMING_URL = "wss://streaming.assemblyai.com/v3/ws"


async def create_streaming_token(api_key: str) -> dict:
    """Mint a short-lived browser token; the permanent AWS key stays on the server."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://streaming.assemblyai.com/v3/token",
                headers={"authorization": api_key},
                params={"expires_in_seconds": 60, "max_session_duration_seconds": 360},
            )
            response.raise_for_status()
            payload = response.json()
            token = payload.get("token") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token.strip() or token == api_key:
                raise TranscriptionError(
                    "Live transcription could not start. Recording is still available."
                )
            return {
                "token": token,
                "websocket_url": STREAMING_URL,
                "sample_rate": 16000,
            }
    except (httpx.HTTPError, ValueError) as exc:
        raise TranscriptionError(
            "Live transcription is unavailable. You can still record a voice note."
        ) from exc


class TranscriptionError(RuntimeError):
    """Safe, actionable transcription error for the UI."""


async def transcribe_audio(raw: bytes, api_key: str) -> str:
    try:
        async with asyncio.timeout(TRANSCRIPTION_TIMEOUT):
            async with httpx.AsyncClient(
                base_url=BASE_URL + "/",
                headers={"authorization": api_key},
                timeout=30,
            ) as client:
                upload = await client.post(
                    "upload",
                    content=raw,
                    headers={"content-type": "application/octet-stream"},
                )
                upload.raise_for_status()
                submitted = await client.post(
                    "transcript",
                    json={
                        "audio_url": upload.json()["upload_url"],
                        "speech_models": ["universal-3-pro", "universal-2"],
                    },
                )
                submitted.raise_for_status()
                transcript = submitted.json()
                started = time.monotonic()
                while transcript.get("status") not in ("completed", "error"):
                    if time.monotonic() - started >= TRANSCRIPTION_TIMEOUT:
                        raise TimeoutError
                    await asyncio.sleep(POLL_INTERVAL)
                    response = await client.get(f"transcript/{transcript['id']}")
                    response.raise_for_status()
                    transcript = response.json()
                if transcript["status"] == "error":
                    raise TranscriptionError(
                        "AssemblyAI could not transcribe this recording. Please record again or retry."
                    )
                return transcript.get("text") or ""
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            detail = "AssemblyAI rejected the transcription key. Check its AWS secret and account access."
        elif exc.response.status_code == 429:
            detail = "AssemblyAI is busy or your transcription quota was reached. Please retry shortly."
        else:
            detail = "AssemblyAI could not process the recording. Please retry shortly."
        raise TranscriptionError(detail) from exc
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise TranscriptionError(
            "Transcription took too long. Please retry or record a shorter message."
        ) from exc
    except httpx.RequestError as exc:
        raise TranscriptionError(
            "Cannot reach AssemblyAI. Please retry when the connection is available."
        ) from exc
