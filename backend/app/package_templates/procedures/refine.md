# Refine a spec against the repo

The specs were written before this code existed or was read, so their `Files:` and `Verify:` are plans. Before a
spec's first task:

1. **Files.** For each task, check each path: it exists, or its folder fits the layout in the conventions file.
   Correct paths to the real ones, and add the test file a task needs if none is named.
2. **Verify.** Check each command runs in this repo: the test runner exists and the script names are right. Correct
   what does not.
3. **Nothing else.** Do not change Do, the order, or any decision. If a task cannot fit the repo without changing
   what it builds, write the question in `.ai/questions.md` and stop.
4. **Show the user the spec's diff** and ask them to approve it before any task runs.

Done when every Files path and Verify command of the spec is real and the user approved the change.
