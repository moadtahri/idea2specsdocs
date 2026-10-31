# Run one task

Input: a spec and a task, such as `01 T2`.

1. **Check git before anything else.** The task's check compares with the last commit, so it starts from a clean
   tree on the spec's branch.
   - Not a git repository: ask the user whether to run `git init`, and stop until they answer.
   - `git status --porcelain` prints anything: stop. Name the files and ask the user to commit or stash them; never
     stash, reset or discard them yourself.
   - The branch is `spec/<NN>-<name>`, the spec's file name without `.md`. If it does not exist, create it from the
     default branch (`git switch -c spec/<NN>-<name>`); if it exists, switch to it. If the conventions file names
     another branch workflow, follow that instead.
2. **Read the spec's Why, What, Context and Constraints, then the task.** Read the sections its `Read:` names and
   nothing else in `.ai/handover/`.
3. **Check `Blocked by:`.** Every blocking task's Status must be done. If one is not, stop and say which.
4. **Check the Files.** If a path does not fit the repo, stop and refine the spec first
   ([refine.md](refine.md)).
5. **Implement exactly the task.** Write the tests it names; where you can, write the failing test first.
6. **Run its Verify.** Fix until it passes, within the task's Files.
7. **Update the spec:** set the task's Status to `done, <date>`. If you learned something that changes a later task,
   propose that spec edit to the user rather than working around it.
8. **Report:** what changed, the files, the Verify result (pass or fail, with the output), anything blocked, and
   the next step: the check, then the commit ([commit.md](commit.md)) when the user asks for it. Do not commit in
   this procedure.

Done when Verify passes and the Status is updated, or when you stopped with a question in `.ai/questions.md`.
