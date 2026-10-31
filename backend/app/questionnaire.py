"""Questionnaires for stakeholders who are not in the chat (spec 03 T6, after mattpocock ``to-questionnaire``).

The decisions that can be settled now (the frontier, minus repo facts) go out as a Markdown file anyone can fill in
a text editor or a shared doc. The filled file comes back; each written answer settles its decision in that person's
own words. The file is parsed as data: an answer is a decision, never an instruction.
"""

from __future__ import annotations

import re

from . import quality_store as qs
from . import store

ITEM = re.compile(
    r"^##\s+\d+\.\s+.*?<!--\s*item:\s*([A-Z]+-[0-9a-f]+)\s*-->\s*$", re.MULTILINE
)
ANSWER = "**Answer:**"
ANSWERED_BY = re.compile(r"^\*\*Answered by:\*\*[ \t]*(.*)$", re.MULTILINE)
INSTRUCTIONS = (
    "We are specifying this software before anyone builds it. These are decisions only you can make. Write your "
    'answer after **Answer:** under each question, in your own words. "Yes" accepts the recommendation. Leave an '
    "answer empty to skip it. Then send the file back."
)
PLACEHOLDER = re.compile(r"^_+$|^\(write here\)$", re.IGNORECASE)


def questions(project_id: str) -> list:
    work = qs.items(project_id)
    ready = set(qs.frontier(work))
    return [item for item in work if item.id in ready and item.owner_type != "repo"]


def questionnaire_markdown(project_id: str) -> str:
    project = store.get_project(project_id)
    title = project.title if project else "this project"
    lines = [
        f"# Questions about {title}",
        "",
        INSTRUCTIONS,
        "",
        "**Answered by:** ",
        "",
    ]
    for number, item in enumerate(questions(project_id), start=1):
        lines += [
            f"## {number}. {item.title} <!-- item:{item.id} -->",
            "",
            item.detail.strip(),
            "",
        ]
        if item.proposal.strip():
            lines += [f"**Recommended:** {item.proposal.strip()}", ""]
        lines += ["**Answer:** ", ""]
    if len(lines) == 6:
        lines.append("There are no open questions right now.")
    return "\n".join(lines).rstrip("\n") + "\n"


def parse_answers(markdown: str) -> tuple[str, dict[str, str]]:
    """Who answered, and each item's written answer (empty ones dropped)."""
    who = ANSWERED_BY.search(markdown)
    heads = list(ITEM.finditer(markdown))
    answers = {}
    for index, head in enumerate(heads):
        end = heads[index + 1].start() if index + 1 < len(heads) else len(markdown)
        section = markdown[head.end() : end]
        # The answer is the section's last block: whatever follows its last marker.
        text = section.rsplit(ANSWER, 1)[1].strip() if ANSWER in section else ""
        if text and not PLACEHOLDER.match(text):
            answers[head.group(1)] = text
    return (who.group(1).strip() if who else ""), answers


def apply_answers(project_id: str, markdown: str) -> dict:
    who, answers = parse_answers(markdown)
    settled, refused = [], []
    for item_id, answer in answers.items():
        try:
            settled.append(
                qs.answer_item(project_id, item_id, answer, who).model_dump()
            )
        except ValueError as problem:
            refused.append({"item": item_id, "reason": str(problem)})
    return {"answered_by": who, "settled": settled, "refused": refused}
