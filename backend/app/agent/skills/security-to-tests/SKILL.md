---
name: security-to-tests
description: Turn security findings into explicit controls and negative tests.
---

# Security requirements and test coverage

For each threat or gap, identify a positive required control, enforcement location,
stable SEC ID, affected interfaces, failure behavior and a QA test reference.
Read the current security blueprint before drafting or revising QA. Enumerate ALL
exact SEC IDs, preserving zero padding. For each, map at least one defined TC case
in the QA plan, using an explicit control-to-case table. A mention in introductory
prose or a reference to a nonexistent TC does not establish coverage. Reuse existing
cases when appropriate; add cases for missing behavior. Do not renumber existing IDs.
Each test contract needs fixtures/setup, steps or attack payload, expected outcomes
and prohibited side effects, automation location or repeatable manual procedure,
priority, and environment requirements. Include negative tests for each applicable
authorization boundary, validation/abuse limit, secret-exposure path and data-deletion
guarantee. Cite which requirement it verifies; do not infer security intent from a
generic functional test. One case may cover multiple controls only when its procedure
and assertions cover each. A mapping is not proof that the procedure is adequate:
independently check it against every MUST in the control. Run check_bundle_contracts
after saving QA and repair missing mappings before claiming completion. Where an
approved not-applicable decision exists, include a TC entry explaining that decision
and how its boundary is checked; do not silently drop the control.
Review authentication modes, development bypasses, authorization and tenancy,
secrets, validation, uploads, abuse prevention, rate limits, retention and logging
as applicable to the target service. Numeric limits are proposals until confirmed.
Distinguish a missing DESIGN from a documented control that still needs CODE or
production verification. Do not claim a control has been implemented or tested from
its presence in a spec. Planned experiments are not completed experiments.
Cite the actual text, record the applicable phase, and require test evidence for
claims such as passed, verified or de-risked. An uploaded result is supplied evidence,
not a test executed by itos. Identify its code revision, environment and coverage.
