# Trial: does this change how you evaluate a robot release?

This is a 30-minute evaluation of a self-hosted tool, written for a robotics engineer who has never seen this
repository. You do not need to read any of its code.

## What the tool does

You give it the recorded episodes of two robot releases (a baseline and a candidate): what each robot **reported**
(succeeded, failed, timed out) and an **independent measurement** of what actually happened (a simulator's ground
truth, a motion-capture pose, a scale, a camera). It checks each report against the measurement, counts the
episodes where they disagree, and asks the OpenMHS engine whether the candidate is a regression, an improvement,
no change, or **there is not enough evidence to say**, with confidence intervals. Every number carries the engine
build, the mapping and the input checksums, and the report regenerates identically.

What we want to learn from you: whether that makes a release decision easier or more trustworthy than the analysis
you would write yourself, and where it does not.

## What you need

- Docker with the Compose plugin, git, a POSIX shell (Git Bash or WSL on Windows), Python 3.10+ for Part B.
- About 9 minutes for the first build (512 s on a GitHub runner; the engine is compiled inside the image). We have not measured disk use.
- Read access to the repository. It is private: the owner will give you access or send you a source archive.
  Nothing else of ours is needed: no credentials, keys or private services.

## Install

```bash
git clone <repository-url> physical-ai-platform
cd physical-ai-platform
bash trial/start.sh
```

It prints `Ready: http://127.0.0.1:3000`. Open it and sign in on **Settings** with any name (a labelled development
identity; it listens on this machine only). If port 3000 or 8000 is taken:
`PAP_WEB_PORT=3100 PAP_API_PORT=8100 bash trial/start.sh`.

`bash trial/start.sh stop` stops it and keeps your data; `bash trial/start.sh reset` deletes everything.

## Do the exercise

1. Read [LIMITATIONS.md](LIMITATIONS.md) (3 minutes).
2. Follow [EXERCISE.md](EXERCISE.md): Part A with the platform, Part B with a plain script.
3. Fill in [FORM.md](FORM.md) and send it back.

## The data

- **MuJoCo reaching arm: simulation.** We generated it. A baseline controller, a variant with 20 ms more command
  latency (a regression we injected on purpose), and an unchanged re-run as a control.
- **CoreSense drone flights: real recordings** of three Crazyflie drones under motion capture (public dataset,
  CC BY 4.0, Zenodo 10.5281/zenodo.23243295). Not a software comparison: see the limitations.

Reports and the full write-ups are in `examples/mujoco-regression/` and `examples/coresense/`.

## Honesty notes

- No external engineer has tried this yet. The dry run in [DRY_RUN.md](DRY_RUN.md) is our own pass through these
  instructions, and says where we got stuck.
- If the plain script is better than the platform for something, we want to know. The comparison is meant to be fair.
- Please do not be polite. A clear "I would not use this, because..." is the most useful thing you can send us.

## Pointers

[PILOT_BRIEF.md](PILOT_BRIEF.md) is a two-page technical summary for teams considering a pilot on their own data.
