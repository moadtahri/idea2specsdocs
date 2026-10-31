---
name: {{skill}}
description: Builds {{project}} from its specs, one task per session. Use to run, check, commit or refine a task from .ai/specs/ ("/{{skill}} task 01 T2", "/{{skill}} check 01 T2", "/{{skill}} commit 01 T2", "/{{skill}} refine 02").
---

# Building {{project}}

The decisions are made: the specs in `.ai/specs/` say what to build, the handover documents in `.ai/handover/` hold
the contracts, and `.ai/decisions.md` records what the project owners decided and why. This skill holds none of
those decisions. It is how you work.

## The loop

1. **One task per fresh session.** Before a spec's first task, refine it: [procedures/refine.md](procedures/refine.md).
2. **Run the task:** [procedures/task.md](procedures/task.md).
3. **Check the diff:** [procedures/check.md](procedures/check.md).
4. **Commit when the user asks:** [procedures/commit.md](procedures/commit.md). Then the next task, in a new
   session.

## Rules that always hold

- **Only the task.** Its Files, its `Read:` sections, nothing adjacent: no drive-by refactors, no extra features.
- **No dependency the spec does not name.**
- **Stop at a missing decision.** When the code or a document contradicts the spec, or the task needs a decision
  nobody made, write the question in `.ai/questions.md` and tell the user. Never choose an answer yourself: these
  questions go back to the project owners.
- **One branch per spec, one commit per task.** The branch is `spec/<NN>-<name>`; the commit subject is
  `<NN>-T<n>: <task title>`. Start a task only from a clean tree, and commit only when the user asks. Never push,
  amend, skip hooks, or discard the user's changes.
- **Trace requirement IDs** (FR-, NFR-, SEC-, API-, DB-, TC-) in tests and commit messages.
- **Done means Verify passed**, not that the code looks right.

## Where things are

| You need | Read |
|---|---|
| what to build next | `.ai/specs/README.md` |
| the stack, layout and commands | `{{conventions}}` |
| a task | its spec in `.ai/specs/`, that task's section only |
| a contract the task cites | only the `Read:` section it names, in `.ai/handover/` |
| why something was decided | `.ai/decisions.md` |
| where to put an unanswered question | `.ai/questions.md` |

### Specs

{{spec_table}}

### Handover documents

{{doc_table}}
