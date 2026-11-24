# Information architecture

| Destination | Existing routes and context |
|---|---|
| Projects | / lists accessible projects. Project pages retain org and project slugs. |
| Studio | Explore models and recordings in /twin. Configure in /experiments and /workflows. The /journey flow connects the laboratory steps. |
| Runs | /workbench keeps the selected workflow run and its journal. /twin selects a recording and optional comparison. /agent retains session history. |
| Integrations | /hardware describes environments and capabilities. /integrations exposes connection and engine details. |
| Settings | /settings handles identity, membership and credentials within the caller’s role. |

Preserve bookmarks and route parameters. A workflow run, an experiment trial, an agent session and a release evaluation have different identities. Joining them requires explicit stored references. Selecting the latest recording of a project cannot establish a relationship to a selected workflow run.

The global header shows the five primary destinations. Detailed pages remain addressable through the `Ctrl K` page finder, which preserves route parameters when a user opens a result. On narrow viewports, the primary row scrolls horizontally below the brand and account controls.
