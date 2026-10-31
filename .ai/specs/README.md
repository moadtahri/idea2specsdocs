# itos specs

## Where this is going

The user brings one of three things: a **new idea**, a **codebase plus a feature**, or a **codebase to redo or
clean up**. Wizi asks only what a stakeholder can answer (budget, purpose, users, UX, what must not change),
proposes engineering defaults for approval, and leaves repo facts to the coding agent. It produces two bundles from
one store:

- **for people:** PRD and design with diagrams;
- **for coding agents:** a skill package. `SKILL.md` holds the loop and the document map; specs, design sections and
  scripts are loaded on demand (progressive disclosure), each task naming what to `Read:`.

Wizi's own harness follows the lessons of the Canyas director harness (Kanya): limits and breakers, a core skill
with pinned stage files, state on disk, summary-first tool results, isolated long reading, and pass-rate evals.

## The specs

Detailed when started, not before. Change a spec when the work teaches something.

| # | Spec | What it delivers | Status |
|---|---|---|---|
| 01 | [harness-resilience](01-harness-resilience.md) | Turn limits, tool-failure breaker, model retry and fallback, compaction | done (live check passed) |
| 02 | [core-skill-and-stages](02-core-skill-and-stages.md) | Core skill in the system prompt; the app places the stage file; intake modes (idea, feature, cleanup); discovery in grilling rounds | done (live check passed) |
| 03 | [decision-ownership](03-decision-ownership.md) | Each decision owned by stakeholder, engineering default or repo, with blocking edges; the decision map (frontier glowing); typed answers settle decisions; later, typed approvals and questionnaires | done (T5 typed approvals, T6 questionnaires) |
| 04 | [repo-reader](04-repo-reader.md) | A read-only subagent for uploaded source that returns a short report; cleanup mode locks current behaviour with tests first and sequences wide refactors expand, migrate, contract | done (live check passed) |
| 05 | [agent-package](05-agent-package.md) | A specs stage (plan, conventions, one spec per slice, each approved) and the zip package: skill with task/check/refine procedures, specs with `Read:` into the nine documents, decisions, questions; later, the human bundle's Mermaid diagrams | done (live checks passed) |
| 06 | [package-checks](06-package-checks.md) | Mechanical checks (every task has Verify, `Read:` links resolve, SKILL.md size, no decisions inside the skill, every step has a done-condition) and the `.ai/questions.md` return path | done (live check passed) |
| 07 | [behaviour-evals](07-behaviour-evals.md) | Real-model cases over several trials, run before and after each change from 02 on | done (baseline recorded) |

## Borrowed practice

Adapted in our own words, credited in `backend/app/agent/skills/SOURCES.md`, never loaded at runtime from upstream.

| Source | Practice | Spec |
|---|---|---|
| Canyas director harness (own) | Breakers, compaction, core skill plus stage files, state on disk, summary-first tools, evals over trials | 01, 02, 04, 07 |
| [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) `grilling` | Questions as a decision tree asked in rounds, each with a recommended answer; facts are looked up, decisions asked | 02, 03 |
| `to-questionnaire` | A questionnaire for the stakeholder who is not in the chat | 03 |
| `to-tickets` | Vertical slices with blocking edges; expand, migrate, contract for wide refactors | 04, 05 |
| `domain-modeling` | `GLOSSARY.md`, and ADRs only for hard-to-reverse, surprising trade-offs | 05 |
| `wizard` | A script for the steps only a human can do (secrets, cloud setup, cutover) | 05 |
| `writing-for-agents` | Pointers worded for when to read; steps that end on a checkable done-condition | 05, 06 |
| `code-review` | Review a diff on two axes, standards and spec | 05 (the package's `check`) |
| Owain Lewis, spec-driven development | Why / What / Constraints / Tasks with Files and Verify; one task per fresh session | 05 |

## Working a task

Fresh session, one task: `read .ai/specs/01-harness-resilience.md and implement T1`. Run its Verify step, set its
`Status`, and stop. See [CLAUDE.md](../../CLAUDE.md) for commands.
