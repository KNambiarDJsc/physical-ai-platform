# Evaluation form

Copy this file, fill it in, and send it back (email or issue, as agreed). Answer from what actually happened;
"I don't know" and "it didn't work" are useful answers. Nothing here is graded, and criticism is the point. If the
script was faster or simpler than the platform for something, say so plainly.

## 1. About you (optional, a line is enough)

- Role and the kind of robots you work with:
- How you evaluate a software or policy release today:
- Operating system, and whether Docker was already installed:

## 2. Installation

| | |
|---|---|
| Time from `git clone` to the web page opening | ___ min |
| Did `bash trial/start.sh` work first time? | yes / no |
| Steps you had to do that the README did not say | |
| Errors or warnings you saw (paste them) | |

## 3. Part A: the platform

| Task | Minutes | Matched the check? (yes / no, and what you got instead) | Blocked or confused at |
|---|---|---|---|
| T1 workspace | | | |
| T2 compare baseline and 20 ms | | | |
| T3 explain one failure | | | |
| T4 did nothing change? | | | |
| T5 real robot data | | | |
| T6 reproducibility | | | |

- Manual work: roughly how many fields, clicks or copy-pastes did T2 take? ___ Was any of it avoidable?
- Anything the platform told you that you did not understand or did not trust:
- Anything you looked for and could not find:

## 4. Part B: the script (or your own tools)

| Task | Minutes | Same answer as the platform? | Notes |
|---|---|---|---|
| S1 same as T2 | | | |
| S2 same as T4 | | | |
| S3 same as T5 | | | |
| S4 explain one failure | | | |

- Did you use our script or your own tools? Which?
- Where was the script **faster or simpler** than the platform?
- Where was the platform faster or better than the script?

## 5. Findings and decisions

- What did the evidence show about the 20 ms regression? (one or two sentences, your words)
- Did the platform and the script lead you to the same conclusion? If not, why?
- Did the reported-versus-measured split (the "Contradiction" episodes) change what you would conclude? How?
- Did the no-change control (T4) make you trust the verdicts more, less, or no differently?
- What would you need to see before using this to support a real release decision?

## 6. Reproducibility

- Were your two JSON reports identical (T6)? yes / no
- Could you explain to a colleague, from the HTML report alone, which software, data and rules produced a verdict?

## 7. Perceived value (circle one per line; 1 = not at all, 5 = very much)

| | | | | | |
|---|---|---|---|---|---|
| The verdicts were clear | 1 | 2 | 3 | 4 | 5 |
| I could trace a verdict back to individual episodes | 1 | 2 | 3 | 4 | 5 |
| Setting up my own data would be easy | 1 | 2 | 3 | 4 | 5 |
| This would save my team time compared with what we do now | 1 | 2 | 3 | 4 | 5 |
| I would trust a report from this in a release review | 1 | 2 | 3 | 4 | 5 |

- Free text: the one change that would matter most to you:
- Would your team run a pilot on its own data? What would have to be true first?
- May we quote your answers (with or without your name)? yes, named / yes, anonymous / no
