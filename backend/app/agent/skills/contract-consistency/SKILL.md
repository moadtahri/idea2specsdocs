---
name: contract-consistency
description: Reconcile brief, PRD, architecture, API, database and tests.
---

# Contract consistency review

Trace approved decisions and stable FR/NFR/AC/SEC/API/DB/OPS/TC IDs across documents.
Compare roles, identifiers, entity ownership, lifecycle states, types, nullability,
validation, pagination, errors, side effects, transactions, migrations and rollback.
Follow the project's chosen stack; never inherit itos's SQLite or chat assumptions.
Repeated IDs with different wording are not automatically contradictions: explain
the incompatible behaviors and cite both locations. Resolve conflicts explicitly;
document precedence does not silently approve a contradictory requirement.
Map each proposed correction to affected documents. A changed deletion decision may
require PRD, API authorization, security and QA changes without a schema change.
Return specific supported findings, not an overall praise score. Inspect every
named gap, including ranges such as G1–G5; do not discuss only two and call all five checked.
