import asyncio

from app import main, store

from .test_workflows import write_doc


def test_rename_preserves_project_and_invalidates_readable_bundle(client, project):
    before = store.get_project(project)
    path = write_doc(project)
    fingerprint = store.docs_fingerprint(project)
    store.write_human_bundle_cache(project, fingerprint, "Old title")
    response = client.patch(
        f"/api/projects/{project}", json={"title": "  Renamed project  "}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed project"
    assert store.get_project(project).thread_id == before.thread_id
    assert path.exists()
    updated = store.docs_fingerprint(project)
    assert updated != fingerprint
    assert store.read_human_bundle_cache(project, updated) is None


def test_delete_removes_every_project_artifact_and_keeps_other_projects(
    client, project
):
    other = store.create_project("Keep this project")
    other_doc = write_doc(other.project_id)
    write_doc(project)
    uploaded = client.post(
        f"/api/projects/{project}/uploads",
        files={"file": ("notes.txt", b"requirements", "text/plain")},
    ).json()
    paths = [
        store.DATA_DIR / f"{project}{suffix}"
        for suffix in (".db", ".db-wal", ".db-shm", ".db-journal")
    ]
    for path in paths:
        path.write_bytes(b"checkpoint data")
    store.write_human_bundle_cache(project, store.docs_fingerprint(project), "Summary")
    paths.append(store.DATA_DIR / f"{project}.bundle-readable.md")
    response = client.delete(f"/api/projects/{project}")
    assert response.status_code == 204
    assert store.get_project(project) is None
    assert not (store.PROJECTS_DIR / project).exists()
    assert not any(path.exists() for path in paths)
    assert store.get_attachments(project, [uploaded["attachment_id"]]) == []
    assert store.get_project(other.project_id) is not None
    assert other_doc.exists()
    assert client.delete(f"/api/projects/{project}").status_code == 404


def test_delete_stops_active_work_before_removing_files(client, project):
    directory = write_doc(project).parent.parent

    async def check():
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def working():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                (directory / "final-cleanup.txt").write_text("Written before deletion")
                stopped.set()

        task = asyncio.create_task(working())
        await started.wait()
        main._active_chats.add(project)
        main._chat_tasks[project] = task
        response = await main.delete_project(project)
        assert response.status_code == 204
        assert task.cancelled()
        assert stopped.is_set()
        assert project not in main._active_chats
        assert project not in main._chat_tasks
        assert not directory.exists()

    asyncio.run(check())


def test_delete_stops_readable_bundle_generation(client, project):
    async def check():
        task = asyncio.create_task(asyncio.sleep(100))
        await asyncio.sleep(0)
        main._bundle_tasks[project] = {task}
        main._bundle_reads[project] = 1
        response = await main.delete_project(project)
        assert response.status_code == 204
        assert task.cancelled()
        assert project not in main._bundle_tasks
        assert project not in main._bundle_reads

    asyncio.run(check())


def test_rename_rejects_blank_and_unknown_projects(client, project):
    assert (
        client.patch(f"/api/projects/{project}", json={"title": "   "}).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/projects/not-a-project", json={"title": "New title"}
        ).status_code
        == 404
    )
