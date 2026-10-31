"""Verify the running server with disposable project data and optional public audio."""

import json
import shutil
import sys
import time
from uuid import UUID

import httpx

from app import store

if __name__ == "__main__":
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        print("Live health:", client.get("/api/health").json(), flush=True)
        if "--transcription" in sys.argv:
            audio = httpx.get(
                "https://assembly.ai/wildfires.mp3", follow_redirects=True, timeout=30
            )
            audio.raise_for_status()
            response = client.post(
                "/api/transcribe",
                files={"file": ("sample.mp3", audio.content, "audio/mpeg")},
            )
            print(
                "Live transcription:",
                response.status_code,
                response.json().get("text", response.json().get("detail", ""))[:160],
                flush=True,
            )
            response.raise_for_status()
        created = client.post(
            "/api/projects", json={"title": "[verification] Temporary todo discussion"}
        )
        created.raise_for_status()
        project_id = str(UUID(created.json()["project_id"]))
        try:
            attachment_ids = []
            for filename, text in [
                (
                    "requirements.txt",
                    "A todo app for personal tasks. Users add, complete and delete tasks.",
                ),
                (
                    "constraints.md",
                    "# Constraints\nA small local MVP, no account system. Discuss before writing handover docs.",
                ),
            ]:
                response = client.post(
                    f"/api/projects/{project_id}/uploads",
                    files={"file": (filename, text.encode(), "text/plain")},
                )
                response.raise_for_status()
                attachment_ids.append(response.json()["attachment_id"])
            started = time.monotonic()
            types = []
            text = []
            with client.stream(
                "POST",
                "/api/chat",
                json={
                    "project_id": project_id,
                    "message": "I want a todo list app. Read both attached notes, discuss the scope and ask at most two focused questions. Do not write documents yet.",
                    "attachment_ids": attachment_ids,
                },
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:])
                    types.append(event["type"])
                    if len(types) == 1:
                        print(
                            "First progress event after",
                            round(time.monotonic() - started, 2),
                            "seconds:",
                            event.get("text"),
                            flush=True,
                        )
                    if event["type"] == "token":
                        text.append(event["text"])
                    if event["type"] == "error":
                        raise RuntimeError(event["detail"])
            assert types[0] == "status" and "done" in types and text
            print(
                "Live text + two attachments: passed. Response:",
                "".join(text)[:220],
                flush=True,
            )
        finally:
            with store._connect() as connection:
                connection.execute(
                    "DELETE FROM attachments WHERE project_id = ?", (project_id,)
                )
                connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            directory = (store.PROJECTS_DIR / project_id).resolve()
            if directory.parent != store.PROJECTS_DIR.resolve():
                raise RuntimeError(
                    "Verification cleanup target is outside the projects directory"
                )
            if directory.exists():
                shutil.rmtree(directory)
            for suffix in (".db", ".db-wal", ".db-shm"):
                (store.DATA_DIR / f"{project_id}{suffix}").unlink(missing_ok=True)
            print("Removed the temporary verification project.", flush=True)
