# Skill sources and adaptations

All skills are application-owned instructions loaded from these packaged files, never installed into the user's IDE
and never fetched from upstream at runtime.

## wizi-core

`wizi-core/SKILL.md` is always in wizi's system prompt; the app adds one file from `stages/` for the project's
stage and, for the feature and cleanup intake modes, one from `modes/`. The layout (a short core skill plus stage
files placed by the app rather than read on request) follows the Canyas director harness
(`canyas-video-director`), an in-house project.

`stages/discovery.md` adapts, in its own words, two sets of MIT-licensed material:

- Pawel Huryn's pm-skills (phuryn/pm-skills), inspected on 2026-10-26; license in `LICENSE.pm-skills`:
  - https://github.com/phuryn/pm-skills/blob/main/pm-product-discovery/skills/interview-script/SKILL.md
  - https://github.com/phuryn/pm-skills/blob/main/pm-execution/skills/create-prd/SKILL.md

  The adaptation adds vertical/service-first clarification, a structured brief, an explicit approval gate,
  service-specific lifecycle questions and itos tools. It omits interview scheduling, unrelated installation
  instructions and automatic web research before requirements are agreed.
- Matt Pocock's skills (mattpocock/skills), inspected on 2026-10-30; license in `LICENSE.mattpocock-skills`:
  - https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md

  Taken: open decisions as a tree asked in rounds, only questions whose prerequisites are settled, a recommended
  answer per question worded so "yes" accepts it, and facts looked up rather than asked. Changed for founders: at
  most three questions per round, and no sub-agent dispatch before the brief is approved.

`modes/cleanup.md` sequences wide refactors as expand, migrate, contract, after mattpocock/skills
`skills/engineering/to-tickets/SKILL.md` (same license).

## Review playbooks

`product-completeness`, `contract-consistency`, `security-to-tests` and `deployment-readiness` are authored for
itos.
