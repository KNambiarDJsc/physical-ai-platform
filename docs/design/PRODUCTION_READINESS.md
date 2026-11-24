# Production readiness and risks

| Risk | Control | Evidence to retain |
|---|---|---|
| Incorrect tenant or reviewer | Workspace-scoped service queries and independent approval bound to exact checksum | Isolation and experiment authorization suites |
| Duplicate or unsafe execution | Worker leases, dispatch journal, idempotency and simulated-only checks | Recovery and workflow tests |
| A convincing explanation masks missing evidence | Read stored engine verdict, expose source identifiers and unknown states | OpenMHS audit and recording investigation e2e |
| Model or simulator unavailable | Show provider and host state. Keep proposal and run state separate | Provider failure, session and host tests |
| Cost or memory grows with selection changes | Load session controls on demand. Keep artifact upload and capture streaming | Measure retained memory and requests on long traces |

Existing automated checks do not establish customer acceptance. Physical environments have discovery and read access. Real Gazebo, live identity-provider and external storage checks need their designated environments. Record exact suite results and skips for each redesign checkpoint.
