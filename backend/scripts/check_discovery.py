"""Live model smoke check; creates and always deletes its own disposable project.

Run inside the API container: python -m scripts.check_discovery
"""

import json

import httpx
from app import store
from app.quality_models import BRIEF_FIELDS
from app.schemas import DOC_SLUGS


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=180) as client:
        response = client.post(
            "/api/projects", json={"title": "Disposable live discovery evaluation"}
        )
        response.raise_for_status()
        project = response.json()["project_id"]
        url = f"/api/projects/{project}"
        try:
            upload = client.post(
                f"{url}/uploads",
                files={
                    "file": (
                        "salon.txt",
                        b"Vertical: independent hair salons. Service: customers book haircut appointments with stylists. One salon, one local time zone. No payment collection or marketplace. Existing workflow is booking by phone. Owner controls schedules. Need to clarify cancellation, double bookings, customer identity and retention. Goal: reduce phone calls.",
                        "text/plain",
                    )
                },
            )
            upload.raise_for_status()
            tools = []
            text = ""
            with client.stream(
                "POST",
                "/api/chat",
                json={
                    "project_id": project,
                    "message": "Use the uploaded context to clarify my requirements before creating a bundle. Ask the next useful questions.",
                    "attachment_ids": [upload.json()["attachment_id"]],
                },
            ) as stream:
                stream.raise_for_status()
                for line in stream.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:])
                    assert event["type"] != "error", event.get("detail")
                    if event["type"] == "tool_call":
                        tools.append(event["name"])
                    if event["type"] == "token":
                        text += event["text"]
            assert text.strip(), "No readable discovery reply"
            assert text.count("?") <= 3, "Discovery bundled too many questions into one reply"
            assert not {"write_file", "edit_file", "write_todos", "task"} & set(
                tools
            ), tools
            assert any(
                term in text.lower() for term in ("salon", "haircut", "stylist")
            ), text
            assert any(
                term in text.lower()
                for term in ("cancel", "book", "schedule", "appoint")
            ), text
            assert not store.has_any_doc(project)
            print(
                "PASS live discovery: supplied vertical/service used; no premature plan or document writes."
            )
            print(text)

            brief = {
                field: "As stated in the supplied owner context"
                for field in BRIEF_FIELDS
            }
            brief.update(
                vertical="Partner marketing",
                service="Invite partners to publish customer stories",
                purpose="Collect approved customer stories",
                users="Partners and admins",
                workflows="Invite, draft, review and publish",
                scope="MVP portal only",
                permissions="Partners edit their stories; deletion ownership unresolved",
                data_lifecycle="Version retention and search scope unresolved",
                constraints="Production bucket and SES access pending",
                success_criteria="Approved stories publish without unauthorized access",
            )
            proposal = client.put(f"{url}/brief", json=brief).json()
            client.post(
                f"{url}/brief/approve", json={"revision": proposal["revision"]}
            ).raise_for_status()
            directory = store.PROJECTS_DIR / project / "docs"
            docs = {
                "prd": "# Partner portal\nFR-1: Partners edit their own customer stories.\nOpen questions: Who can delete a story? How long are versions retained? Does search include story text or only customer metadata?\n",
                "technical-spike": "# Spike\nStatus: completed.\nExperiment plan: Test Cognito token validation and S3 upload CORS after implementation. No execution output or result artifacts supplied.\n",
                "sad-architecture": "# Architecture\nFastAPI modular monolith and React; Cognito identity, S3 uploads, SES invitations. Ownership and lifecycle follow FR-1.\n",
                "api-specification": "# API\nAPI-1: PATCH /stories/{id} enforces FR-1.\nAPI-2: GET /stories?q= matches customer name and email only.\n",
                "database-schema": "# Data\nDB-1: artifact_versions is append-only. Pruning policy is unresolved.\n",
                "security-blueprint": "# Security\nSEC-1: Production must reject X-User-Email bypass headers.\nG1–G5 must be fixed before launch.\nG1: Dev header leak.\nG2: Missing rate limits on login and invites.\n",
                "devops-iac-spec": "# Deployment\nOPS-1: Configure S3_BUCKET; startup must reject missing values. Production value TBD.\nSES is sandbox-only; production access needs owner and cutover plan.\n",
                "qa-test-plan": "# QA\nTC-1: Verify FR-1 authorized edits and denial for other partners.\nTC-2: Verify SEC-1 rejects development headers.\n",
                "runbook": "# Operations\nRollback by redeploying the previous immutable image. Confirm database compatibility first.\n",
            }
            for slug in DOC_SLUGS:
                (directory / f"{slug}.md").write_text(docs[slug], encoding="utf-8")
            result = client.post(f"{url}/reviews", json={"environment": "production"})
            result.raise_for_status()
            report = result.json()
            assert report["status"] == "complete", report
            assert report["findings"], "Reviewer missed all seeded semantic gaps"
            state = client.get(f"{url}/quality").json()
            assert (
                not state["ready_for_implementation"]
                and not state["ready_for_production"]
            )
            assert any(
                "G3, G4, G5" in finding["detail"] for finding in state["findings"]
            )
            print(
                "PASS live independent review: validated citations and conservative readiness."
            )
            print(
                json.dumps(
                    {
                        "summary": report["summary"],
                        "findings": [
                            finding["title"] for finding in report["findings"]
                        ],
                    },
                    indent=2,
                )
            )
        finally:
            client.delete(url).raise_for_status()


if __name__ == "__main__":
    main()
