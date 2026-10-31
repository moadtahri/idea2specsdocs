# Commit one task

Input: a spec and a task, such as `01 T2`. Run this only when the user asks for the commit, after they reviewed the
check's findings.

1. **The task is done.** Its Status in the spec is `done, <date>` and the check ran
   ([check.md](check.md)). If either is missing, stop and say which.
2. **The branch is the spec's.** `git branch --show-current` is `spec/<NN>-<name>`, the spec's file name without
   `.md`. If it is not, stop and say so: do not commit on another branch.
3. **Stage only the task.** `git add` each changed path in the task's Files, and the spec file. Never `git add -A` or
   `git add .`. Run `python .claude/skills/{{skill}}/scripts/check_scope.py .ai/specs/<NN>-<name>.md T<n>` again:
   anything it lists that the user did not accept in the check stays unstaged, and you say so.
4. **Write the message.** The subject is `<NN>-T<n>: <task title>`, the title as the spec's `### T<n>:` heading
   writes it. The body lists the requirement IDs the task covers (FR-, NFR-, SEC-, API-, DB-, TC-) and the Verify
   result in one line:

   ```text
   01-T2: Booking API

   Requirements: FR-3, API-2, TC-7
   Verify: pytest -q tests/test_bookings.py passed (6)
   ```

5. **Commit.** `git commit` with that message. Never `--amend`, never `--no-verify`, never push. If a hook fails, fix
   the cause within the task's Files and commit again, or stop and show the user the hook's output.
6. **Report** the commit's short hash and subject, and the next task. The next task starts in a new session.

Done when the commit exists on the spec's branch with only the task's files, or when you stopped and said why.
