import pytest
from fastapi.testclient import TestClient

from app import main, store


@pytest.fixture
def client(tmp_path, monkeypatch):
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    monkeypatch.setattr(store, "DATA_DIR", data)
    monkeypatch.setattr(store, "REGISTRY_DB", data / "app.db")
    monkeypatch.setattr(store, "PROJECTS_DIR", projects)
    monkeypatch.setattr(main, "PROJECTS_DIR", projects)
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def project(client):
    return client.post("/api/projects", json={"title": "Feature planning"}).json()[
        "project_id"
    ]
