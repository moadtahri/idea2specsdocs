---
name: deployment-readiness
description: Separate deployment inputs and launch checks from implementation blockers.
---

# Deployment readiness review

Review the target environment, configuration contract, external account/service
dependencies, ownership, credentials, origins/CORS, storage, email delivery,
observability, backups, migrations, cutover and rollback as applicable.
A production value that will be injected at deployment need not block implementation
if its name, validation, owner, usage and verification are defined. An undefined
behavior or missing control is a different finding. Classify each explicitly.
Use stable OPS IDs and map launch requirements to checks and supplied results.
Specify who supplies missing inputs and what demonstrates readiness. Do not invent
account approvals, cloud configuration, delivery capacity or completed rollout.
Ready-for-implementation, implementation-verified and ready-for-production are
different claims. Return evidence-backed findings for this exact bundle revision
and environment; no "perfect" or unconditional launch assurances.
