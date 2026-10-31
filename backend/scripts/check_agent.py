"""Run one isolated chat turn through the full agent stack."""

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import main, store

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="idea2specs-agent-check-") as tmp:
        root = Path(tmp)
        store.DATA_DIR = root / "data"
        store.REGISTRY_DB = store.DATA_DIR / "app.db"
        store.PROJECTS_DIR = root / "projects"
        main.PROJECTS_DIR = store.PROJECTS_DIR
        with TestClient(main.app) as client:
            project = client.post(
                "/api/projects", json={"title": "Agent connectivity check"}
            ).json()
            response = client.post(
                "/api/chat",
                json={
                    "project_id": project["project_id"],
                    "message": "Reply briefly that the agent is ready. Do not write files.",
                },
            )
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        errors = [event["detail"] for event in events if event.get("type") == "error"]
        if response.status_code != 200 or errors:
            print("Full agent check failed:", errors or response.status_code)
            raise SystemExit(1)
        print(
            "Full agent check passed; events:",
            ", ".join(event["type"] for event in events),
        )
