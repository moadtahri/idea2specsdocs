import asyncio
import re
from types import SimpleNamespace

import pytest
from langchain.messages import AIMessage, SystemMessage

from app import store
from app.agent import factory, stages
from app.agent.factory import scoped_env
from app.agent.prompts import ORCHESTRATOR_PROMPT
from app.agent.quality_skills import CORE_DIR, CORE_FILES, load_core_file
from app.quality_models import BRIEF_FIELDS
from app.schemas import DOC_SLUGS


def approve_brief(client, project, **extra):
    brief = {field: f"Confirmed {field}" for field in BRIEF_FIELDS} | extra
    state = client.put(f"/api/projects/{project}/brief", json=brief).json()
    client.post(
        f"/api/projects/{project}/brief/approve", json={"revision": state["revision"]}
    )


def write_docs(project, slugs):
    docs = store.PROJECTS_DIR / project / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for slug in slugs:
        (docs / f"{slug}.md").write_text(f"# {slug}\n", encoding="utf-8")


def test_core_skill_stays_small_and_loads_without_frontmatter():
    core = load_core_file("SKILL.md")
    assert len(core) < 7_000
    assert not core.startswith("---")
    assert ORCHESTRATOR_PROMPT.endswith(core)


def test_every_file_the_core_skill_names_exists():
    core = (CORE_DIR / "SKILL.md").read_text(encoding="utf-8")
    for stage in ("discovery", "drafting", "review"):
        assert f"| {stage} |" in core
    for name in CORE_FILES:
        assert load_core_file(name).strip()
    with pytest.raises(ValueError):
        load_core_file("../requirements.py")


def test_stage_follows_the_brief_and_the_documents(client, project):
    directory = store.PROJECTS_DIR / project
    assert stages.current_stage(directory) == "discovery"
    approve_brief(client, project)
    assert stages.current_stage(directory) == "drafting"
    write_docs(project, DOC_SLUGS[:-1])
    assert stages.current_stage(directory) == "drafting"
    write_docs(project, DOC_SLUGS[-1:])
    assert (
        stages.current_stage(directory) == "specs"
    )  # then review once the specs exist (test_package.py)


@pytest.mark.parametrize(
    ("mode", "files"),
    [
        ("idea", ["stages/drafting.md"]),
        ("feature", ["stages/drafting.md", "modes/feature.md"]),
        ("cleanup", ["stages/drafting.md", "modes/cleanup.md"]),
    ],
)
def test_mode_adds_its_file_in_every_stage(mode, files):
    assert stages.stage_files("drafting", mode) == files


def test_stage_text_is_added_to_string_and_block_system_messages():
    added = stages.with_text(SystemMessage(content="core"), "Stage: x")
    assert added.content == "core\n\nStage: x"
    blocks = stages.with_text(
        SystemMessage(content=[{"type": "text", "text": "core"}]), "Stage: x"
    )
    assert blocks.content[-1] == {"type": "text", "text": "Stage: x"}
    assert stages.with_text(None, "Stage: x").content == "Stage: x"


def test_middleware_adds_the_current_stage_before_each_call(client, project):
    directory = store.PROJECTS_DIR / project
    middleware = stages.StageMiddleware(directory)
    seen = []

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**vars(self), **changes})

    def handler(request):
        seen.append(request.system_message.content)
        return AIMessage(content="ok")

    middleware.wrap_model_call(
        Request(system_message=SystemMessage(content="core"), messages=[]), handler
    )
    approve_brief(client, project, intake="cleanup")
    middleware.wrap_model_call(
        Request(system_message=SystemMessage(content="core"), messages=[]), handler
    )
    assert "# Stage: discovery" in seen[0] and "# Mode:" not in seen[0]
    assert "# Stage: drafting" in seen[1] and "# Mode: cleanup" in seen[1]


def test_real_graph_shows_wizi_the_discovery_stage(client, project, monkeypatch):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.outputs import ChatGeneration, ChatResult

    systems = []

    class Model(BaseChatModel):
        @property
        def _llm_type(self):
            return "stage-test"

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            systems.append(str(messages[0].content))
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="Q1?"))]
            )

    monkeypatch.setattr(factory, "build_llm", Model)

    async def run():
        directory = store.PROJECTS_DIR / project
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                await graph.ainvoke(
                    {"messages": [("user", "A booking app for vets")]},
                    {"configurable": {"thread_id": project}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    asyncio.run(run())
    [system] = systems
    assert "# Wizi" in system and "# Stage: discovery" in system
    assert re.search(r"Ask in rounds", system)
    assert "# Stage: drafting" not in system


def test_intake_defaults_to_idea_and_never_counts_as_missing(client, project):
    state = client.put(
        f"/api/projects/{project}/brief", json={"vertical": "Vets"}
    ).json()
    assert state["brief"]["intake"] == "idea"
    assert "intake" not in state["missing"]
    assert stages.intake(store.PROJECTS_DIR / project) == "idea"


def test_intake_accepts_only_the_three_modes(client, project):
    assert (
        client.put(
            f"/api/projects/{project}/brief", json={"intake": "feature"}
        ).status_code
        == 200
    )
    assert stages.intake(store.PROJECTS_DIR / project) == "feature"
    assert (
        client.put(
            f"/api/projects/{project}/brief", json={"intake": "rewrite"}
        ).status_code
        == 422
    )
