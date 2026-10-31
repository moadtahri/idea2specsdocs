from app import specs, store
from app.agent import stages
from app.quality_models import BRIEF_FIELDS
from app.schemas import DOC_SLUGS

PLAN = """# Spec plan

1. [00-foundation.md](00-foundation.md): scaffold, tests, CI
2. [01-booking-core.md](01-booking-core.md): book a slot; waits on 00
3. 01-booking-core.md again, mentioned twice
"""


def ready_project(client, project):
    brief = {field: f"Confirmed {field}" for field in BRIEF_FIELDS}
    state = client.put(f"/api/projects/{project}/brief", json=brief).json()
    client.post(
        f"/api/projects/{project}/brief/approve", json={"revision": state["revision"]}
    )
    directory = store.PROJECTS_DIR / project
    (directory / "docs").mkdir(parents=True, exist_ok=True)
    for slug in DOC_SLUGS:
        (directory / "docs" / f"{slug}.md").write_text(
            f"# {slug}\n\n## Overview\n", encoding="utf-8"
        )
    return directory


def write_spec(directory, name, text="# spec\n"):
    folder = specs.specs_dir(directory)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_plan_lists_specs_in_order_without_repeats(client, project):
    directory = store.PROJECTS_DIR / project
    assert specs.planned(directory) == []
    write_spec(directory, "README.md", PLAN)
    assert specs.planned(directory) == ["00-foundation.md", "01-booking-core.md"]


def test_spec_names_are_the_plan_the_conventions_or_numbered():
    assert specs.is_spec_name("README.md") and specs.is_spec_name("agents.md")
    assert specs.is_spec_name("03-cancel-and-reschedule.md")
    for bad in ("3-x.md", "01_booking.md", "../01-x.md", "01-X.md", "notes.md"):
        assert not specs.is_spec_name(bad)


def test_specs_stage_lasts_until_every_planned_spec_exists(client, project):
    directory = ready_project(client, project)
    assert stages.current_stage(directory) == "specs"
    assert specs.missing(directory) == ["README.md", "agents.md"]
    write_spec(directory, "README.md", PLAN)
    write_spec(directory, "agents.md")
    assert specs.missing(directory) == ["00-foundation.md", "01-booking-core.md"]
    write_spec(directory, "00-foundation.md")
    assert stages.current_stage(directory) == "specs"
    write_spec(directory, "01-booking-core.md")
    assert specs.missing(directory) == []
    assert stages.current_stage(directory) == "review"
    assert [path.name for path in specs.spec_files(directory)] == [
        "README.md",
        "agents.md",
        "00-foundation.md",
        "01-booking-core.md",
    ]


def test_the_specs_stage_file_is_what_wizi_sees(client, project):
    directory = ready_project(client, project)
    text = stages.stage_text(directory)
    assert text.startswith("# Stage: specs")
    assert ".ai/handover/" in text and "**Verify:**" in text
    assert "write the next file in the same turn" in text
    assert text.endswith(
        "Still to write, in order: `/specs/README.md`, `/specs/agents.md`."
    )
    write_spec(directory, "README.md", PLAN)
    write_spec(directory, "agents.md")
    write_spec(directory, "00-foundation.md")
    assert stages.stage_text(directory).endswith(
        "Still to write, in order: `/specs/01-booking-core.md`."
    )


SPEC = """# 01 Booking core

## Why
FR-1.

## Tasks

### T1: Booking model
**Do:** Add the booking model.
**Files:** `app/models.py`, `tests/test_models.py`
**Read:** `.ai/handover/database-schema.md#overview`
**Verify:** `pytest tests/test_models.py`
**Blocked by:** none
**Status:** todo

### T2: Booking route
**Files:** `app/routes/`
"""


def packaged(client, project, intake="idea"):
    import io
    import zipfile

    from app import package
    from app import quality_store as qs
    from app.quality_models import WorkItemInput

    directory = ready_project(client, project)
    if intake != "idea":
        brief = client.get(f"/api/projects/{project}/quality").json()["brief"]["brief"]
        state = client.put(
            f"/api/projects/{project}/brief", json={**brief, "intake": intake}
        ).json()
        client.post(
            f"/api/projects/{project}/brief/approve",
            json={"revision": state["revision"]},
        )
    write_spec(
        directory,
        "README.md",
        "# Plan\n\n1. [01-booking-core.md](01-booking-core.md)\n",
    )
    write_spec(directory, "agents.md", "# Conventions\n\nRun `pytest`.\n")
    write_spec(directory, "01-booking-core.md", SPEC)
    first = qs.propose_item(
        project,
        WorkItemInput(
            kind="product_decision",
            title="Guest booking",
            detail="Account or guest?",
            affected_docs=["prd"],
        ),
    )
    qs.settle_item(
        project, first.id, "guests", "Guests book without an account", "guests please"
    )
    data = package.package_zip(project)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def test_idea_package_has_the_skill_specs_documents_and_conventions(client, project):
    files = packaged(client, project)
    skill = ".claude/skills/build-feature-planning"
    for name in (
        "SKILL.md",
        "procedures/task.md",
        "procedures/check.md",
        "procedures/refine.md",
        "procedures/commit.md",
        "scripts/check_scope.py",
    ):
        assert f"{skill}/{name}" in files
    assert files["AGENTS.md"].startswith("# Conventions") and files[
        "CLAUDE.md"
    ].startswith("@AGENTS.md")
    assert ".ai/specs/README.md" in files and ".ai/specs/01-booking-core.md" in files
    assert ".ai/specs/agents.md" not in files
    assert all(f".ai/handover/{slug}.md" in files for slug in DOC_SLUGS)
    assert (
        "`.ai/specs/01-booking-core.md` | 01 Booking core" in files[f"{skill}/SKILL.md"]
    )
    assert not [name for name, text in files.items() if "{{" in text]
    decisions = files[".ai/decisions.md"]
    assert (
        "## Guest booking" in decisions
        and 'The owner\'s words:** "guests"' in decisions
    )
    assert ".ai/questions.md" in files and ".ai/README.md" in files


def test_the_skill_works_on_a_branch_per_spec_and_a_commit_per_task(client, project):
    files = packaged(client, project)
    skill = ".claude/skills/build-feature-planning"
    assert "/build-feature-planning commit 01 T2" in files[f"{skill}/SKILL.md"]
    task = files[f"{skill}/procedures/task.md"]
    assert "git status --porcelain" in task and "spec/<NN>-<name>" in task
    assert "Do not commit in\n   this procedure" in task
    commit = files[f"{skill}/procedures/commit.md"]
    assert "`<NN>-T<n>: <task title>`" in commit
    assert "Never `git add -A`" in commit and "never push" in commit
    assert "/build-feature-planning commit 00 T1" in files[".ai/README.md"]


def test_existing_repositories_keep_their_own_conventions_files(client, project):
    files = packaged(client, project, intake="feature")
    assert "AGENTS.md" not in files and "CLAUDE.md" not in files
    assert files[".ai/AGENTS.md"].startswith("# Conventions")
    assert "`.ai/AGENTS.md`" in files[".claude/skills/build-feature-planning/SKILL.md"]
    assert "already has conventions" in files[".ai/README.md"]


def test_check_scope_flags_files_outside_the_task_and_new_dependencies(tmp_path):
    import subprocess
    import sys

    from app.package import TEMPLATES

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "models.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / ".ai" / "specs").mkdir(parents=True)
    spec = tmp_path / ".ai" / "specs" / "01-booking-core.md"
    spec.write_text(SPEC, encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    script = str(TEMPLATES / "scripts" / "check_scope.py")

    def check(task):
        return subprocess.run(
            [sys.executable, script, ".ai/specs/01-booking-core.md", task],
            check=False,  # the exit code is what the test reads
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    (tmp_path / "app" / "models.py").write_text(
        "class Booking: ...\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_models.py").write_text("", encoding="utf-8")
    spec.write_text(
        SPEC.replace("**Status:** todo", "**Status:** done"), encoding="utf-8"
    )
    ok = check("T1")
    assert ok.returncode == 0, ok.stdout + ok.stderr

    (tmp_path / "app" / "views.py").write_text("", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = ['requests']\n", encoding="utf-8"
    )
    flagged = check("T1")
    assert flagged.returncode == 1
    assert "app/views.py" in flagged.stdout and "pyproject.toml" in flagged.stdout
    assert check("T9").returncode == 2


def test_package_route_and_spec_files_in_the_document_list(client, project):
    import io
    import zipfile

    assert client.get(f"/api/projects/{project}/package").status_code == 404
    directory = ready_project(client, project)
    write_spec(
        directory,
        "README.md",
        "# Plan\n\n1. [01-booking-core.md](01-booking-core.md)\n",
    )
    write_spec(directory, "01-booking-core.md", SPEC)
    docs = client.get(f"/api/projects/{project}/docs").json()["docs"]
    titles = {doc["slug"]: doc["title"] for doc in docs}
    assert titles["spec-README"] == "Spec plan"
    assert titles["spec-01-booking-core"] == "Spec · 01 Booking core"
    assert "bundle-agent" in titles  # the single-file bundle stays
    assert (
        client.get(f"/api/projects/{project}/docs/spec-01-booking-core").json()[
            "markdown"
        ]
        == SPEC
    )
    assert (
        client.get(f"/api/projects/{project}/docs/spec-..%2Fsecret").status_code == 404
    )
    response = client.get(f"/api/projects/{project}/package")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        'filename="feature-planning-agent-package.zip"'
        in response.headers["content-disposition"]
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert ".ai/specs/01-booking-core.md" in archive.namelist()


def test_right_after_a_saved_spec_wizi_is_told_to_write_the_next(client, project):
    from langchain.messages import HumanMessage, ToolMessage

    directory = ready_project(client, project)
    write_spec(directory, "README.md", PLAN)
    write_spec(directory, "agents.md")
    saved = ToolMessage(
        content="Updated file /specs/agents.md", tool_call_id="w1", name="write_file"
    )
    text = stages.stage_text(directory, [HumanMessage("Write the specs"), saved])
    assert text.endswith(
        "The user approved `/specs/agents.md` and it is saved: no card is waiting. Write `/specs/00-foundation.md` "
        "now, in this turn, after one line on what it covers. Do not ask whether to continue."
    )
    failed = ToolMessage(
        content="Error: /specs/agents.md",
        tool_call_id="w2",
        name="write_file",
        status="error",
    )
    for messages in ([HumanMessage("hi")], [saved, HumanMessage("thanks")], [failed]):
        assert "no card is waiting" not in stages.stage_text(directory, messages)
