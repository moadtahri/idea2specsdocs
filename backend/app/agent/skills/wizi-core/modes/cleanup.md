# Mode: cleanup

An existing codebase to redo or clean up. This is where coding agents do the most damage: a cleanup without a lock
on current behaviour turns into a rewrite. This workflow specifies the cleanup; it does not perform it.

- **Discovery asks what only the owner knows:** which behaviour must be kept exactly and for whom, what may change
  or be dropped, the acceptable risk and downtime, the time budget, and why now (the pain the cleanup removes). Look
  up everything else in the source.
- **Inventory current behaviour through `repo-reader`.** Call `task` with `repo-reader`, the source folder
  (`/uploads/<id>/source/`) and the question "inventory the behaviours users depend on: entry points, data stores,
  integrations, and the highest seam where each can be tested". Never read the snapshot yourself. Keep its observed
  claims (with files) apart from assumed ones, and record repo facts as `owner_type` `repo` items.
- **Lock behaviour first.** The first implementation task always records current behaviour as tests at the highest
  seam available. Every later task is verified by those tests still passing.
- **Wide changes go expand, migrate, contract.** A change that breaks callers across the codebase (a renamed column,
  a retyped shared symbol) is sequenced: add the new form beside the old, migrate callers in batches (each batch its
  own task), then remove the old form once nothing uses it.
- **Every step can be undone.** Give each task its rollback. Never call a refactor safe without tests that ran.
