# Recorded deviations

This file records known departures from the approved Specs workflow so they are visible in the repository. It is not Specs authority: it does not change a requirement, accept a risk, or replace a decision. A formal decision or risk record, if wanted, is made through the Specs change process by the Updater role.

| ID | Deviation | Source and date | Scope | Consequence | Closes when |
|---|---|---|---|---|---|
| DV-01 | Ponytail: the Specs workflow (`development-workflow.md` section 4) pins `v4.13.0` and blocks Claude Code tasks until the pin is verified. The installed plugin, version 5.1.0 in `full` mode, is used instead. | Stated and confirmed by JDC in the Claude Code session on 2026-10-09 (the user stated they are JDC; this is a session statement, not a Specs record). | All Claude Code work in this repository. | Gate 8 Ponytail evidence comes from an unpinned, unverified tool. Its output remains finding input only. `RISK-0005` stays Draft in the Specs. | `TASK-05` verifies the pin, or the Specs record an approved change. |
| DV-02 | Local Python is 3.12.10, not the pinned 3.12.15. python.org publishes no Windows binary for 3.12.15. | Environment constraint found 2026-10-09. | Local development and local test runs only. CI and the container base remain the pinned version. | Local results are for the same 3.12 series, not proof for 3.12.15. | CI pins 3.12.15 (`TASK-04`) or a container run exists (`TASK-27`). |

## Status of the confirmation

JDC confirmed DV-01 in the session on 2026-10-09. That confirmation lives only in the session and this file: no DEC or RISK change exists in the frozen Specs, and `RISK-0005` there stays Draft. A formal Specs-side record, if wanted, is made by the Updater role through the Specs change process. Until then, treat DV-01 as a JDC-confirmed deviation, not a Specs change; it closes when `TASK-05` verifies the pin or the Specs record an approved change.
