"""Run one Part B command, keep its output, print how long it took (used by trial/dry_run.sh).

python3 trial/time_part_b.py OUT_DIR mujoco A D
"""

from __future__ import annotations

import subprocess
import sys
import time

out, *args = sys.argv[1:]
start = time.perf_counter()
run = subprocess.run([sys.executable, "trial/baseline/analysis.py", *args], capture_output=True, text=True, check=True)
took = time.perf_counter() - start
with open(f"{out}/part-b.txt", "a", encoding="utf-8") as f:
    f.write(f"$ python trial/baseline/analysis.py {' '.join(args)}\n{run.stdout}\n")
print(f"script_seconds[{'_'.join(args)}]={took:.2f}")
