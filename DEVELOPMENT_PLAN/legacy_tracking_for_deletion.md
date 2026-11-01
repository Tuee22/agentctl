# Shapes Tracked for Deletion

**Status**: Authoritative source
**Supersedes**: N/A

> **Purpose**: Name each shape still standing in the tree that the architecture does not want, where
> it is, why it must go, and the one phase whose work deletes it.

A row names a shape that is still present, its location, why it must go, and exactly one deleting
phase, which exists and is not Done; `plan.legacy-ledger` checks the header and the deleting phase.
The ledger schedules nothing: the deleting phase's own Remaining Work states the deletion, and a row
leaves the table in the same change that removes its shape. An empty table is the healthy state. A
shape that must never return is held out by an absence guard, a test or validator check, rather than
by a row here, and a shape the design never builds is explained in
[rationale.md](rationale.md#rejected-alternatives).

## Tracked Shapes

| Shape | Location | Why it must go | Deleted by |
|---|---|---|---|

The table is empty.

## Related

- [development_plan_standards.md](development_plan_standards.md) — § I defines absence guards and this
  ledger.
- [rationale.md](rationale.md#rejected-alternatives) — explains shapes the design never builds; this
  file holds only shapes still standing.
- [README.md](README.md) — the status table that says whether a deleting phase is Done.
