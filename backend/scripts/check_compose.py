"""Exercise the Compose stack through Nginx, including persistence and cancellation."""

import argparse
import json
import os
import time
from uuid import UUID

import httpx

from app import store

MARKER = store.DATA_DIR / "compose-smoke.json"
TITLE = "itos persistent smoke project"
DOCUMENT = "# Compose verification\n\nFR-1: Users can complete tasks.\n"


def create(client, title):
    response = client.post("/api/projects", json={"title": title})
    response.raise_for_status()
    return str(UUID(response.json()["project_id"]))


def seed(client):
    if MARKER.exists():
        raise RuntimeError(
            "A smoke marker already exists. Run --cleanup before seeding again."
        )
    project_id = create(client, "Temporary Compose check")
    renamed = client.patch(f"/api/projects/{project_id}", json={"title": TITLE})
    renamed.raise_for_status()
    uploaded = client.post(
        f"/api/projects/{project_id}/uploads",
        files={
            "file": (
                "notes.md",
                b"A personal todo app with add, complete and delete actions.",
                "text/markdown",
            )
        },
    )
    uploaded.raise_for_status()
    path = store.PROJECTS_DIR / project_id / "docs" / "prd.md"
    path.write_text(DOCUMENT, encoding="utf-8")
    store.write_human_bundle_cache(
        project_id,
        store.bundle_fingerprint(project_id),
        "# Readable smoke overview\nA personal todo app.",
    )
    MARKER.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "attachment_id": uploaded.json()["attachment_id"],
            }
        ),
        encoding="utf-8",
    )
    print(
        "Seeded a disposable project, rename, upload, document and readable bundle.",
        flush=True,
    )


def verify(client, live):
    marker = json.loads(MARKER.read_text(encoding="utf-8"))
    project_id = marker["project_id"]
    projects = client.get("/api/projects").json()
    assert any(
        project["project_id"] == project_id and project["title"] == TITLE
        for project in projects
    )
    assert (
        client.get(f"/api/projects/{project_id}/docs/prd").json()["markdown"]
        == DOCUMENT
    )
    assert client.get(f"/api/projects/{project_id}/docs/prd/download").text == DOCUMENT
    assert (
        "FR-1"
        in client.get(f"/api/projects/{project_id}/docs/bundle-agent").json()[
            "markdown"
        ]
    )
    assert (
        "Readable smoke overview"
        in client.get(f"/api/projects/{project_id}/docs/bundle").json()["markdown"]
    )
    assert (
        store.PROJECTS_DIR
        / project_id
        / "uploads"
        / f"{marker['attachment_id']}.context.txt"
    ).exists()
    print(
        "Persistent registry, uploads, documents, downloads and bundles: passed.",
        flush=True,
    )
    if live:
        started = time.monotonic()
        events = []
        with client.stream(
            "POST",
            "/api/chat",
            json={
                "project_id": project_id,
                "message": "Discuss the attached todo-app notes briefly. Introduce yourself by name. Do not write any files.",
                "attachment_ids": [marker["attachment_id"]],
            },
        ) as response:
            response.raise_for_status()
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                events.append(event)
                if len(events) == 1:
                    delay = time.monotonic() - started
                    assert event["type"] == "status" and delay < 2
                    print(
                        "First proxied SSE progress event:",
                        round(delay, 3),
                        "seconds",
                        flush=True,
                    )
                if event["type"] == "error":
                    raise RuntimeError(event["detail"])
        assert any(event["type"] == "done" for event in events)
        answer = "".join(event["text"] for event in events if event["type"] == "token")
        assert answer
        assert store.checkpoint_path(project_id).exists()
        print(
            "Live wizi discussion, attachment input and checkpoint: passed.", flush=True
        )


def delete_active(client):
    project_id = create(client, "Disposable cancellation check")
    with client.stream(
        "POST",
        "/api/chat",
        json={"project_id": project_id, "message": "Plan a todo app"},
    ) as stream:
        stream.raise_for_status()
        for line in stream.iter_lines():
            if line.startswith("data:"):
                assert json.loads(line[5:])["type"] == "status"
                break
        deleted = client.delete(f"/api/projects/{project_id}")
        deleted.raise_for_status()
        assert deleted.status_code == 204
    assert client.get(f"/api/projects/{project_id}/docs").status_code == 404
    assert not (store.PROJECTS_DIR / project_id).exists()
    assert not store.checkpoint_path(project_id).exists()
    print(
        "Delete during active work: stopped wizi and removed all project data.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ("seed", "verify", "live", "delete-active", "cleanup"):
        parser.add_argument("--" + option, action="store_true")
    options = parser.parse_args()
    with httpx.Client(
        base_url=os.environ.get("ITOS_TEST_URL", "http://web:8080"), timeout=180
    ) as client:
        page = client.get("/")
        assert page.status_code == 200 and "itos" in page.text
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["transcription_provider"] == "assemblyai"
        print("itos frontend and proxied API health: passed.", flush=True)
        if options.seed:
            seed(client)
        if options.verify:
            verify(client, options.live)
        if options.delete_active:
            delete_active(client)
        if options.cleanup:
            marker = json.loads(MARKER.read_text(encoding="utf-8"))
            project_id = marker["project_id"]
            client.delete(f"/api/projects/{project_id}").raise_for_status()
            assert not (store.PROJECTS_DIR / project_id).exists()
            assert not store.checkpoint_path(project_id).exists()
            assert store.get_project(project_id) is None
            MARKER.unlink()
            print("Deleted the disposable smoke project and all its files.", flush=True)
