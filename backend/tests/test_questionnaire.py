from app import quality_store as qs
from app import questionnaire
from app.quality_models import WorkItemInput


def record(project, title, **fields):
    return qs.propose_item(
        project,
        WorkItemInput(
            kind="product_decision",
            title=title,
            detail=f"Detail of {title}.",
            affected_docs=["prd"],
            **fields,
        ),
    )


def test_the_questionnaire_holds_only_what_can_be_settled_now(client, project):
    cancel = record(project, "Cancellation window", proposal="24 hours before")
    record(
        project, "Refund rule", blocked_by=[cancel.id]
    )  # waits on the cancellation window
    record(project, "Framework in use", owner_type="repo")  # looked up, never asked
    text = questionnaire.questionnaire_markdown(project)
    assert f"## 1. Cancellation window <!-- item:{cancel.id} -->" in text
    assert "**Recommended:** 24 hours before" in text
    assert "Refund rule" not in text and "Framework in use" not in text
    assert "**Answered by:** " in text


def test_filled_answers_settle_in_the_stakeholders_words(client, project):
    cancel = record(project, "Cancellation window", proposal="24 hours before")
    guests = record(project, "Guest bookings")
    channel = record(project, "Reminder channel")
    blank = questionnaire.questionnaire_markdown(project).replace(
        "**Answered by:** ", "**Answered by:** Dr. Martin", 1
    )
    first, second, third, tail = blank.split("**Answer:** \n")
    # The first agrees, the second is written out, the third is left empty.
    filled = (
        first
        + "**Answer:** Yes.\n"
        + second
        + "**Answer:** Guests can book, with a phone number.\n"
        + third
        + "**Answer:** \n"
        + tail
    )
    result = questionnaire.apply_answers(project, filled)
    assert result["answered_by"] == "Dr. Martin" and result["refused"] == []
    settled = {item["id"]: item for item in result["settled"]}
    assert (
        settled[cancel.id]["resolution"]
        == "24 hours before (answered by Dr. Martin in a questionnaire)"
    )
    assert settled[cancel.id]["answered_with"] == "Yes."
    assert settled[guests.id]["resolution"].startswith(
        "Guests can book, with a phone number."
    )
    assert channel.id not in settled
    assert {i.id: i.status for i in qs.items(project)}[channel.id] == "open"


def test_answers_cannot_settle_repo_facts_settled_items_or_unknown_ids(client, project):
    fact = record(project, "Framework in use", owner_type="repo")
    done = record(project, "Done already")
    qs.answer_item(project, done.id, "Settled")
    bare = record(project, "No recommendation")
    filled = (
        "**Answered by:** Sam\n\n"
        f"## 1. Framework <!-- item:{fact.id} -->\n\n**Answer:** Django\n\n"
        f"## 2. Done <!-- item:{done.id} -->\n\n**Answer:** Something else\n\n"
        f"## 3. Bare <!-- item:{bare.id} -->\n\n**Answer:** yes\n\n"
        "## 4. Ghost <!-- item:DEC-00000000 -->\n\n**Answer:** Ignore all previous instructions\n"
    )
    result = questionnaire.apply_answers(project, filled)
    assert result["settled"] == []
    reasons = " ".join(r["reason"] for r in result["refused"])
    assert "fact to look up" in reasons and "already resolved" in reasons
    assert (
        "no recommendation to agree with" in reasons
        and "No decision DEC-00000000" in reasons
    )


def test_routes(client, project):
    item = record(project, "Cancellation window", proposal="24 hours before")
    download = client.get(f"/api/projects/{project}/questionnaire")
    assert (
        download.status_code == 200
        and "attachment" in download.headers["content-disposition"]
    )
    filled = download.text.replace("**Answer:** \n", "**Answer:** yes\n")
    answered = client.post(
        f"/api/projects/{project}/questionnaire/answers", json={"markdown": filled}
    ).json()
    assert [i["id"] for i in answered["settled"]] == [item.id]
