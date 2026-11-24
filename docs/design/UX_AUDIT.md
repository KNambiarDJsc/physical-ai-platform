# Investigation UX audit

| Finding from source | Engineering consequence | Response |
|---|---|---|
| Workbench had a selected step and verification inspector, while free-form investigation lived on /agent. | Engineers had to transfer run identity manually. | Seed the question from the selected run and step. |
| Twin had event-aware deterministic explanation and separate workspace sessions. | Asking a second question lost the selected event. | Open the session composer beside the recording inspector. |
| Agent page defaults to the workspace’s latest session. | A previous answer could appear to describe the current selection. | Embedded composer opens without a selected answer. |
| Fixed-width side panes competed with the scene; the old shell also spent a full rail on navigation. | The scene had too little room and measurements were harder to reach on narrow screens. | Use a five-destination header and page finder, collapsible source/evidence panels, keyboard-resizable splits, and a scrollable mobile nav row. At 390 px the workspace stacks without page-level horizontal overflow. |

The local skills directory includes Impeccable, Taste and engineering-loop. The browser checks provide automated engineering journeys. Customer task completion times, confusion rates and observed navigation errors require participant sessions.
