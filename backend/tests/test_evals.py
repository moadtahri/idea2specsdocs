"""The eval graders on recorded trials: no server, no model (spec 07)."""

import json

from evals import cases, fixtures, run


def item(id_, status="open", blocked_by=(), answered_with=""):
    return {
        "id": id_,
        "title": id_,
        "status": status,
        "blocked_by": list(blocked_by),
        "answered_with": answered_with,
    }


def discovery_trial(**changes):
    trial = {
        "turns": [
            {
                "text": "For your salon: how far ahead can clients cancel? Who sees bookings?"
            },
            {"text": "ok"},
        ],
        "calls": [
            {"name": "propose_work_item", "args": {}},
            {"name": "task", "args": {"subagent_type": "repo-reader"}},
        ],
        "items_before": [item("A"), item("B", blocked_by=["A"])],
        "frontier_before": ["A"],
        "items_after": [item("A", "resolved", answered_with="yes"), item("B")],
        "docs_written": False,
    }
    return {**trial, **changes}


def test_a_good_discovery_trial_passes_every_check():
    graded = run.grade(cases.DISCOVERY, discovery_trial())
    assert all(outcome["passed"] for outcome in graded.values()), graded


def test_discovery_failures_are_caught():
    graded = run.grade(
        cases.DISCOVERY,
        discovery_trial(
            turns=[{"text": "A? B? C? D?"}, {"text": ""}],
            calls=[
                {"name": "task", "args": {"subagent_type": "architect"}},
                {"name": "write_file", "args": {}},
            ],
            items_before=[item("A")],
            items_after=[
                item("A", "resolved", answered_with="yes"),
                item("B", "resolved"),
            ],
        ),
    )
    assert {name for name, o in graded.items() if o["passed"] is False} == {
        "at_most_three_questions",
        "no_writes_or_specialists",
        "uses_supplied_context",
        "decisions_have_edges",
        "yes_settles_only_the_frontier",
    }
    assert "task:architect" in graded["no_writes_or_specialists"]["note"]


def specs_trial(**changes):
    trial = {
        "turns": [],
        "continued": [True, True],
        "missing": [],
        "spec_text": "Use FastAPI and PostgreSQL. Tests with pytest.",
        "docs_text": "FastAPI, PostgreSQL",
        "register_text": "Test runner: pytest (default, to confirm)",
        "package_blockers": 0,
        "package_findings": [],
    }
    return {**trial, **changes}


def test_specs_checks_pass_when_choices_are_named_somewhere():
    graded = run.grade(cases.SPECS, specs_trial())
    assert all(outcome["passed"] for outcome in graded.values()), graded


def test_specs_checks_catch_stops_new_choices_and_blockers():
    graded = run.grade(
        cases.SPECS,
        specs_trial(
            continued=[True, False],
            spec_text="Models with SQLAlchemy; hours in a YAML file; pip install -r requirements.txt",
            package_blockers=2,
            missing=["03-reminders.md"],
        ),
    )
    assert all(outcome["passed"] is False for outcome in graded.values()), graded
    assert graded["decides_nothing_new"]["note"] == (
        "sqlalchemy in: Models with SQLAlchemy; hours in a YAML file; pip install -r requirements.txt"
        " | yaml in: Models with SQLAlchemy; hours in a YAML file; pip install -r requirements.txt"
        " | requirements.txt in: Models with SQLAlchemy; hours in a YAML file; pip install -r requirements.txt"
    )
    assert (
        graded["continues_after_approval"]["note"]
        == "1/2 approvals led to the next card"
    )


def test_what_a_named_choice_needs_is_not_a_new_decision():
    trial = specs_trial(
        spec_text="requirements: fastapi, httpx; lint config in pyproject.toml",
        docs_text="",
        register_text="",
    )
    assert sorted(cases.unnamed_choices(trial)) == [
        "httpx",
        "toml",
    ]  # nothing names FastAPI or ruff
    ci = specs_trial(
        spec_text="`.github/workflows/ci.yml` runs pytest",
        docs_text="GitHub Actions CI",
        register_text="",
    )
    assert cases.unnamed_choices(ci) == [
        "pytest"
    ]  # YAML is what GitHub Actions reads; pytest is still a choice
    named = {
        **trial,
        "register_text": "Linter: ruff (confirmed)",
        "docs_text": "FastAPI",
    }
    assert cases.unnamed_choices(named) == []


def test_a_trial_that_never_got_there_is_not_counted():
    graded = run.grade(
        cases.SPECS, specs_trial(continued=[], spec_text="", missing=["README.md"])
    )
    assert graded["continues_after_approval"]["passed"] is None
    assert graded["decides_nothing_new"]["passed"] is None
    assert graded["reaches_review"]["passed"] is False


def test_repo_reader_checks():
    good = {
        "turns": [{"text": "Today POST /bookings saves the name and phone."}],
        "calls": [{"name": "task", "args": {"subagent_type": "repo-reader"}}],
        "brief": {"revision": "r1", "brief": {"intake": "feature"}},
    }
    assert all(o["passed"] for o in run.grade(cases.REPO_READER, good).values())
    bad = {
        "turns": [{"text": "Tell me about your app."}],
        "calls": [
            {"name": "read_file", "args": {"file_path": "/uploads/a1.context.txt"}}
        ],
        "brief": {"revision": ""},
    }
    graded = run.grade(cases.REPO_READER, bad)
    assert [graded[c]["passed"] for c in cases.REPO_READER.checks] == [
        False,
        False,
        False,
        None,
    ]
    assert graded["never_reads_the_source_itself"]["note"] == "/uploads/a1.context.txt"


def test_a_missing_field_is_not_reached_rather_than_a_crash():
    graded = run.grade(cases.DISCOVERY, {"turns": []})
    assert all(outcome["passed"] is None for outcome in graded.values())


def test_report_compares_with_an_earlier_run():
    trial = {"checks": {"reaches_review": {"passed": True, "note": ""}}}
    earlier = {"specs": [{"checks": {"reaches_review": {"passed": False, "note": ""}}}]}
    text = run.report({"specs": [trial, trial]}, earlier)
    assert "reaches_review" in text and "2/2   (was 0/1)" in text
    json.dumps({"specs": [trial]})  # results stay JSON-ready


def test_fixtures_are_the_nine_documents_and_a_readable_source():
    from app import source_context
    from app.schemas import DOC_SLUGS

    assert sorted(fixtures.DOCS) == sorted(DOC_SLUGS)
    files, _ = source_context.source_files(fixtures.source_zip())
    assert "salon/app/routes.py" in files


def test_main_calls_reads_wizis_tool_calls_from_the_checkpoint(
    client, project, monkeypatch
):
    # The latest checkpoint holds no messages channel; the calls live in each step's writes.
    import asyncio

    from langchain.messages import AIMessage

    from app import store
    from app.agent import factory
    from app.agent.factory import scoped_env
    from evals.client import main_calls

    from .test_repo_reader import Scripted

    Scripted.replies[:] = [
        AIMessage(
            content="", tool_calls=[{"name": "list_docs", "args": {}, "id": "c1"}]
        ),
        AIMessage(content="done"),
    ]
    monkeypatch.setattr(factory, "build_llm", Scripted)
    directory = store.PROJECTS_DIR / project
    thread = store.get_project(project).thread_id

    async def run():
        with scoped_env(directory):
            graph, manager = await factory.build_agent(
                directory, store.checkpoint_path(project)
            )
            try:
                await graph.ainvoke(
                    {"messages": [("user", "hi")]},
                    {"configurable": {"thread_id": thread}},
                )
            finally:
                await manager.__aexit__(None, None, None)

    asyncio.run(run())
    assert main_calls(project) == [{"name": "list_docs", "args": {}}]


def test_questions_back_checks():
    good = {
        "turns": [
            {
                "text": "The coding agent asks how a guest gets the cancel link.",
                "interrupts": [],
            },
            {
                "text": "",
                "interrupts": [
                    {"name": "edit_file", "path": "/specs/01-booking-core.md"}
                ],
            },
        ],
        "imported": ["DEC-1"],
        "items": [
            {
                "id": "DEC-1",
                "status": "resolved",
                "answered_with": "Put the cancel link in the confirmation email.",
            }
        ],
        "decisions_md": "- **Decision:** Put the cancel link in the confirmation email.",
        "spec_after": "Send the cancel link in the confirmation email.",
    }
    assert all(o["passed"] for o in run.grade(cases.QUESTIONS_BACK, good).values())
    silent = {
        **good,
        "turns": [{"text": "Anything else?", "interrupts": []}],
        "items": [],
        "decisions_md": "",
        "spec_after": "",
    }
    graded = run.grade(cases.QUESTIONS_BACK, silent)
    assert [o["passed"] for o in graded.values()] == [False, False, False, False]
