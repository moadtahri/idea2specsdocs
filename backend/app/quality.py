"""Deterministic checks and conservative, revision-bound readiness assessment."""

import re

from . import quality_store as qs
from . import store
from .agent.quality_skills import load_skill
from .quality_models import SKILL_IDS, Finding

POLICY_VERSION = "2"
ID = re.compile(r"\b(?:FR|NFR|AC|SEC|API|DB|OPS|TC)-\d+\b")
DEFINITION = re.compile(
    r"^\s*(?:#{1,6}\s+|[-*]\s+|\|\s*)?(?:\*\*|`)?((?:FR|NFR|AC|SEC|API|DB|OPS|TC)-\d+)\b"
)


def documents(project_id: str) -> dict[str, str]:
    return {
        slug: path.read_text(encoding="utf-8") if path.exists() else ""
        for slug, path in store._doc_files(project_id)
    }


def definitions(text: str, prefix: str = "") -> set[str]:
    return {
        match[1]
        for line in text.splitlines()
        if (match := DEFINITION.match(line)) and match[1].startswith(prefix)
    }


def security_coverage(docs: dict[str, str]) -> list[dict]:
    """Link explicit SEC references to defined QA cases, never incidental mentions.

    Supports test-case table rows, heading/list case blocks, and traceability
    table rows referencing existing cases. Mapping is a design check, not proof
    that a case is adequate or has executed; the independent reviewer checks that.
    """
    qa_lines = docs["qa-test-plan"].splitlines()
    cases = {}
    for index, line in enumerate(qa_lines):
        match = DEFINITION.match(line)
        if not match or not match[1].startswith("TC-"):
            continue
        end = index + 1
        if not line.lstrip().startswith("|"):
            while end < len(qa_lines):
                following = qa_lines[end]
                if DEFINITION.match(following) or re.match(r"^\s*#{1,6}\s+", following):
                    break
                end += 1
        cases[match[1]] = {
            "test_id": match[1],
            "line": index + 1,
            "excerpt": "\n".join(qa_lines[index:end])[:1200],
            "controls": set(ID.findall("\n".join(qa_lines[index:end]))),
        }
    links = {
        control: set() for control in definitions(docs["security-blueprint"], "SEC-")
    }
    for identifier, case in cases.items():
        for control in links.keys() & case["controls"]:
            links[control].add(identifier)
    for line in qa_lines:
        if line.lstrip().startswith("|"):
            identifiers = set(ID.findall(line))
            for control in links.keys() & identifiers:
                links[control].update(cases.keys() & identifiers)
    result = []
    for index, line in enumerate(docs["security-blueprint"].splitlines(), 1):
        match = DEFINITION.match(line)
        if (
            match
            and match[1] in links
            and not any(row["control_id"] == match[1] for row in result)
        ):
            result.append(
                {
                    "control_id": match[1],
                    "line": index,
                    "control": line[:600],
                    "test_ids": sorted(links[match[1]]),
                    "mapped": bool(links[match[1]]),
                }
            )
    return result


def policy_revision() -> str:
    return qs.digest(
        {"policy": POLICY_VERSION, "skills": [load_skill(name) for name in SKILL_IDS]}
    )


def mechanical_findings(project_id: str) -> list[dict]:
    docs = documents(project_id)
    findings = []

    def add(
        key,
        title,
        detail,
        slugs,
        category="contract-consistency",
        severity="blocker",
        impact="implementation",
        line=None,
    ):
        citation = []
        if line is not None:
            citation = [
                {
                    "slug": slugs[0],
                    "line": line,
                    "quote": docs[slugs[0]].splitlines()[line - 1][:600],
                }
            ]
        findings.append(
            Finding(
                id=key,
                category=category,
                severity=severity,
                impact=impact,
                title=title,
                detail=detail,
                recommendation="Revise the affected contract or record a supported, explicit decision.",
                affected_docs=slugs,
                citations=citation,
            ).model_dump()
        )

    for slug, text in docs.items():
        if not text.strip():
            add(
                f"missing-{slug}",
                f"{store.DOC_TITLES[slug]} is missing",
                "A complete nine-document implementation bundle needs this contract. Available drafts remain downloadable.",
                [slug],
            )
    for slug, prefix in (
        ("prd", "FR-"),
        ("security-blueprint", "SEC-"),
        ("qa-test-plan", "TC-"),
    ):
        if docs[slug].strip() and not definitions(docs[slug], prefix):
            add(
                f"ids-{slug}",
                f"Add stable {prefix} IDs",
                "Requirements and checks need stable identifiers to support traceability and verification coverage.",
                [slug],
            )
    known = set().union(*(definitions(text) for text in docs.values()))
    for item in qs.items(project_id):
        known.update(item.requirement_ids)
    for slug, text in docs.items():
        for number, line in enumerate(text.splitlines(), 1):
            unknown = set(ID.findall(line)) - known
            if unknown:
                add(
                    f"undefined-{slug}-{number}",
                    "Undefined requirement reference",
                    f"These IDs are referenced but not defined: {', '.join(sorted(unknown))}.",
                    [slug],
                    line=number,
                )
            if re.search(r"\b(?:TBD|TODO|TBC)\b", line):
                add(
                    f"placeholder-{slug}-{number}",
                    "Unclassified placeholder",
                    "Classify this placeholder as a product decision, implementation requirement, deployment input or future work. A deployment value need not block implementation when its configuration contract is complete.",
                    [slug],
                    severity="warning",
                    impact="future",
                    line=number,
                )
    for coverage in security_coverage(docs):
        control = coverage["control_id"]
        if not coverage["mapped"]:
            add(
                f"security-test-{control}",
                f"{control} has no QA mapping",
                "Link this exact security ID to a defined TC- test case in the QA plan. Include setup, actions, expected failure/success behavior and automation or a repeatable manual procedure. A prose mention or an undefined test ID is not coverage.",
                ["security-blueprint", "qa-test-plan"],
                category="security-to-tests",
                line=coverage["line"],
            )
    all_text = "\n".join(docs.values())
    gap_definitions = set()
    for line in all_text.splitlines():
        match = re.match(
            r"^\s*(?:#{1,6}\s+|[-*]\s+|\|\s*)?(?:\*\*)?(G\d+)(?:\*\*)?\s*[:.)-]", line
        )
        if match:
            gap_definitions.add(match[1])
    for slug, text in docs.items():
        for number, line in enumerate(text.splitlines(), 1):
            for match in re.finditer(r"\bG(\d+)\s*[-–]\s*G(\d+)\b", line):
                start, end = int(match[1]), int(match[2])
                if 0 < end - start < 50:
                    missing = {
                        f"G{value}" for value in range(start, end + 1)
                    } - gap_definitions
                    if missing:
                        add(
                            f"gaps-{slug}-{number}",
                            "Named gaps are not fully accounted for",
                            "The referenced range contains undefined gaps: "
                            + ", ".join(sorted(missing)),
                            [slug],
                            category="evidence",
                            line=number,
                        )
    return findings


def assessment(project_id: str, environment: str = "production") -> dict:
    docs = documents(project_id)
    spec = qs.spec_revision(project_id)
    evidence_hash = qs.evidence_revision(project_id)
    review = qs.latest_review(project_id)
    current = bool(
        review
        and review["spec_revision"] == spec
        and review["evidence_revision"] == evidence_hash
        and review["environment"] == environment
        and review.get("policy_revision") == policy_revision()
    )
    reviewed = current and review["status"] == "complete"
    findings = mechanical_findings(project_id)
    if current:
        findings += review["findings"]
    items = qs.items(project_id)
    blocking = {phase: 0 for phase in ("specification", "implementation", "production")}
    for finding in findings:
        if finding["severity"] == "blocker" and finding["impact"] in blocking:
            blocking[finding["impact"]] += 1
    for item in items:
        if item.status in ("open", "proposed") and item.impact in blocking:
            blocking[item.impact] += 1
    brief = qs.brief_state(project_id)
    if brief["status"] != "approved":
        blocking["specification"] += 1
    ready = bool(
        reviewed
        and all(text.strip() for text in docs.values())
        and not blocking["specification"]
        and not blocking["implementation"]
    )
    records = qs.evidence(project_id)
    usable = [
        row for row in records if row["spec_revision"] == spec and row["artifact_valid"]
    ]
    impl = [row for row in usable if row["scope"] == "implementation"]
    revision = impl[-1]["source_revision"] if impl else None

    def coverage(scope):
        statuses = {}
        for row in usable:
            if (
                row["scope"] == scope
                and row["source_revision"] == revision
                and (scope != "production" or row["environment"] == environment)
            ):
                for identifier in row["covered_ids"]:
                    statuses[identifier] = row["outcome"]
        return {key for key, value in statuses.items() if value == "passed"}

    required_tests = definitions(docs["qa-test-plan"], "TC-")
    required_launch = (
        definitions(docs["security-blueprint"], "SEC-")
        | definitions(docs["devops-iac-spec"], "OPS-")
        | definitions(docs["runbook"], "OPS-")
    )
    verified = bool(
        ready and required_tests and required_tests <= coverage("implementation")
    )
    production = bool(
        verified
        and not blocking["production"]
        and required_launch
        and required_launch <= coverage("production")
    )
    return {
        "spec_revision": spec,
        "environment": environment,
        "brief": brief,
        "review_status": "not_reviewed"
        if not review
        else "outdated"
        if not current
        else review["status"],
        "review_current": current,
        "last_review": review,
        "draft_available": any(text.strip() for text in docs.values()),
        "ready_for_implementation": ready,
        "implementation_verified": verified,
        "ready_for_production": production,
        "verification_revision": revision,
        "blocking": blocking,
        "findings": findings,
        "items": [item.model_dump() for item in items],
        "frontier": qs.frontier(items),
        "evidence": records,
        "required_test_ids": sorted(required_tests),
        "required_launch_ids": sorted(required_launch),
        "security_coverage": security_coverage(docs),
        "documents": [
            {"slug": slug, "present": bool(text.strip())} for slug, text in docs.items()
        ],
        "verification_note": "Verification is based on user-attested uploaded results for the recorded code revision and environment. itos does not execute uploaded code.",
    }


def bundle_quality_markdown(project_id: str) -> str:
    state = assessment(project_id)
    lines = [
        "## Readiness and decisions",
        "",
        f"- Review: {state['review_status']}",
        f"- Specification revision: {state['spec_revision']}",
        f"- Target environment: {state['environment']}",
        f"- Project brief: {state['brief']['status']}",
    ]
    for key, label in (
        ("ready_for_implementation", "Ready for implementation"),
        ("implementation_verified", "Implementation verified from supplied evidence"),
        ("ready_for_production", "Ready for production"),
    ):
        lines.append(f"- {label}: {'yes' if state[key] else 'not established'}")
    lines += [
        "",
        state["verification_note"],
        "",
        "### Project context (approval status above)",
        "",
    ]
    for field, value in state["brief"]["brief"].items():
        if value:
            lines.append(
                f"- {field.replace('_', ' ').title()}: {value if isinstance(value, str) else '; '.join(value)}"
            )
    lines += ["", "### Shared decisions and requirements", ""]
    if not state["items"]:
        lines.append(
            "No structured decisions have been recorded. This does not establish that there are no unresolved decisions."
        )
    for item in state["items"]:
        lines += [
            f"- {item['id']} — {item['title']} ({item['status']}; {item['impact']}; owner: {item['owner']})",
            f"  - {item['detail']}",
            f"  - Proposal: {item['proposal'] or 'none'}",
            f"  - Decision: {item['resolution'] or 'unresolved'}",
            f"  - Affected: {', '.join(item['affected_docs'])}",
        ]
    lines += [
        "",
        "### Security-to-QA traceability (planned coverage, not executed results)",
        "",
        "| Security control | Defined QA cases |",
        "| --- | --- |",
    ]
    for row in state["security_coverage"]:
        lines.append(
            f"| {row['control_id']} | {', '.join(row['test_ids']) or 'UNMAPPED — implementation blocker'} |"
        )
    lines += ["", "### Current findings", ""]
    for finding in state["findings"]:
        lines += [
            f"- {finding['id']} — {finding['title']} ({finding['severity']}; {finding['impact']})",
            f"  - {finding['detail']}",
            f"  - Next: {finding['recommendation']}",
        ]
        for citation in finding["citations"]:
            lines.append(
                f"  - Evidence: {citation['slug']} line {citation['line']}: {citation['quote']}"
            )
    if not state["findings"]:
        lines.append(
            "No current findings recorded. A current complete review is still required for readiness."
        )
    lines += ["", "### Verification records", ""]
    for record in state["evidence"]:
        lines.append(
            f"- {record['id']}: {record['scope']}, {record['outcome']}, code {record['source_revision']}, environment {record['environment']}; covers {', '.join(record['covered_ids'])}; artifact valid: {record['artifact_valid']}; current specification: {record['spec_revision'] == state['spec_revision']}"
        )
    return "\n".join(lines) + "\n"
