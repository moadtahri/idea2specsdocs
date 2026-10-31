# Check a task's diff

Three separate passes, so one does not colour the next.

1. **Scope.** Run `python .claude/skills/{{skill}}/scripts/check_scope.py .ai/specs/<NN>-<name>.md T<n>` (add
   `--base <ref>` to compare with a commit other than `HEAD`). It lists files changed outside the task's Files and
   dependency manifests that changed. Every line it prints needs a reason or a revert.
2. **Spec.** Does the diff do what Do says, cite its requirement IDs, and respect Must, Must not and Out of scope?
   Run the task's Verify yourself.
3. **Standards.** Does it follow the conventions file and the patterns already in the repo? Is it the simplest thing
   that works? Look for obvious bugs and missing unhappy paths.

Report each finding with its file and line, most severe first. When there are none, say so plainly.

Done when all three passes have run and the findings (or "none") are reported.
