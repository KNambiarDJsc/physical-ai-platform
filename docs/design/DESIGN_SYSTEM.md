# Physical AI Studio — Spatial Engineering Design System

## Two directions

**Instrument desk.** A dark blue-black field, cyan selection, fixed tool edges, tabular readings and one dominant viewport. Spatial awareness from the Lattice brief suits simultaneous scene and time inspection. Runway’s editing-workspace principle keeps the investigation alongside the selected material. Choose this direction for operation and playback.

**Engineering notebook.** A cool neutral field, dark ink, aligned evidence rows and wide margins. This suits reading release reports and approval packets. At workstation density the margins compete with playback. Use its light surfaces for document review.

## Applied direction

Taste dealt `product-performs`, `quiet-instrument` and `type-only-statement`. The product uses `product-performs`: the
interface and its recorded evidence are the proof. On this page, a time-indexed robot event becomes an investigation
bench beside the OpenMHS verdict. A generic telemetry viewer could show the event; this workflow keeps the run identity,
recorded state, criterion and engine result in one place.

Fluid functionalism means the project index, scene and evidence panes reflow with available width. Navigation is text-led;
primary actions are explicit; the app uses stored project data and real recording fragments. The light field is now a cool
neutral. Motion stays limited to route and control feedback, with reduced-motion support.

## Application navigation and workspace

The global header exposes Projects, Studio, Runs, Integrations and Settings. Remaining existing pages stay reachable in
the searchable `Ctrl K` page finder. On phones the navigation becomes a separate horizontal row. Digital twin and
Workbench use collapsible side panels and accessible resizers around the selected scene or run; the timeline remains
visible as the bottom workspace. Below desktop width these panes stack instead of forcing horizontal page scroll.

## Component inventory

| Primitive | Source | Interaction and states |
|---|---|---|
| Split pane | components/Split.tsx | Drag or focus the separator. Arrows resize, Shift increases the step, Home and End reach the bounds. |
| Scene and track | components/twin | A selected event seeks on the recording clock. The event list provides text and keyboard access. Display gaps as unavailable. |
| Investigation disclosure | InvestigationAgent.tsx | Native summary toggles by keyboard. Loading announces progress. Opening seeds an editable question. Ask explicitly starts a session. |
| Session and proposal | Agent.tsx | Show provider availability, role, limits, trace and filing feedback from the API. |
| Outcome | Workbench.tsx, ui.tsx | Label the device report and independent verdict. Keep units next to values and show missing observations in words. |

Geist Sans carries controls and headings. Geist Mono carries identities and tabular numbers. Use the shared accent for action and focus, semantic color plus text for outcome, and the system reduced-motion preference for transitions.
