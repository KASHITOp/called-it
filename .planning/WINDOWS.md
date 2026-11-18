---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 1
total_count: 2
last_updated: 2026-11-18T20:35:14.119Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 01 | stub | data/src/calledit_data/db/check.py | 76 | db check reports FAIL on postgresql (trigger/RLS/replication-role checks deferred to Plan 01-08); --connect-only works | open |  | 2026-11-18T15:00:42.422Z |  |
| 2 | 01 | stub | nowcaster/src/nowcaster/cli.py |  | nowcast calendar prints business_update_at/results_at/reveal_at: none and status: expected for every company; reveal events are stored from Plan 01-04, which must wire them in | fixed |  | 2026-11-18T16:29:09.765Z | 2026-11-18T20:35:14.119Z |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "01",
    "file": "data/src/calledit_data/db/check.py",
    "line": 76,
    "description": "db check reports FAIL on postgresql (trigger/RLS/replication-role checks deferred to Plan 01-08); --connect-only works",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-11-18T15:00:42.422Z",
    "resolved_at": null,
    "milestone": null
  },
  {
    "id": 2,
    "kind": "stub",
    "phase": "01",
    "file": "nowcaster/src/nowcaster/cli.py",
    "line": null,
    "description": "nowcast calendar prints business_update_at/results_at/reveal_at: none and status: expected for every company; reveal events are stored from Plan 01-04, which must wire them in",
    "status": "fixed",
    "reason": "",
    "recorded_at": "2026-11-18T16:29:09.765Z",
    "resolved_at": "2026-11-18T20:35:14.119Z",
    "milestone": null
  }
]
````
