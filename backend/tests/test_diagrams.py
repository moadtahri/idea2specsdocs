from app import diagrams
from app import quality_store as qs
from app.quality_models import WorkItemInput

from .test_package import ready_project, write_spec

FOUNDATION = "# 00 Foundation\n\n## Tasks\n\n### T1: Scaffold\n**Blocked by:** none\n"
BOOKING = '# 01 Booking "core"\n\n## Tasks\n\n### T1: Model\n**Blocked by:** 00-T1\n\n### T2: Route\n**Blocked by:** T1\n'


def test_build_order_follows_cross_spec_blockers(client, project):
    directory = ready_project(client, project)
    write_spec(directory, "README.md", "1. 00-foundation.md\n2. 01-booking-core.md\n")
    write_spec(directory, "00-foundation.md", FOUNDATION)
    write_spec(directory, "01-booking-core.md", BOOKING)
    order = diagrams.build_order(project)
    assert order.splitlines() == [
        "flowchart LR",
        '  s00["00 Foundation"]',
        "  s01[\"01 Booking 'core'\"]",  # a quote would end the label early
        "  s00 --> s01",
    ]


def test_decision_graph_shows_only_linked_decisions(client, project):
    def record(title, **fields):
        return qs.propose_item(
            project,
            WorkItemInput(
                kind="product_decision",
                title=title,
                detail="Detail.",
                affected_docs=["prd"],
                **fields,
            ),
        )

    first = record("Appointment types")
    record("Cancellation window", blocked_by=[first.id])
    record("Logo colour")  # stands alone: not drawn
    qs.answer_item(project, first.id, "Consultation and vaccination")
    graph = diagrams.decision_graph(project)
    assert (
        '["Appointment types"]:::settled' in graph
        and '["Cancellation window"]:::open' in graph
    )
    assert "d1 --> d2" in graph and "Logo colour" not in graph


def test_no_data_means_no_diagram_section(client, project):
    assert diagrams.section(project) == ""


def test_the_readable_bundle_ends_with_fresh_diagrams(client, project, monkeypatch):
    from app import main

    async def summary(source):
        return "# Handover overview\n\nSummary.\n"

    monkeypatch.setattr(main, "summarize_bundle", summary)
    directory = ready_project(client, project)
    write_spec(directory, "00-foundation.md", FOUNDATION)
    first = client.get(f"/api/projects/{project}/docs/bundle").json()["markdown"]
    assert "## Diagrams" in first and "```mermaid\nflowchart LR" in first
    write_spec(
        directory, "01-booking-core.md", BOOKING
    )  # a new spec: the cached summary is reused, diagrams are not
    second = client.get(f"/api/projects/{project}/docs/bundle").json()["markdown"]
    assert "s00 --> s01" in second and "s00 --> s01" not in first
