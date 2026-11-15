"""One command to reproduce everything:  .venv/bin/python run_validation.py
Add --skip-download to reuse data/processed/ instead of re-fetching."""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
PY = sys.executable
skip = "--skip-download" in sys.argv
import os
have_login = (Path.home() / ".netrc").exists() or bool(os.environ.get("EARTHDATA_TOKEN"))

steps = []
if not skip:
    steps += ["fetch_lidar_tide.py", "s2.py", "s1.py"]
    if have_login:
        steps.append("nisar.py")
    else:
        print("!! No Earthdata login (~/.netrc or EARTHDATA_TOKEN): NISAR step skipped. "
              "Run: .venv/bin/python src/earthdata_login.py")
# Rebuild boundaries, score sensors, generate the Bayesian reconstruction,
# then create and independently check the report.
steps += [
    "lidar_boundaries.py",
    "lidar_sanity.py",
    "score.py",
    "reconstruct.py",
    "figures.py",
    "make_report.py",
    "selfcheck.py",
    "make_report.py",
]

for s in steps:
    print(f"\n===== {s} =====", flush=True)
    r = subprocess.run([PY, s], cwd=SRC)
    if r.returncode != 0:
        sys.exit(f"step {s} failed")
print("\nDone. See outputs/, outputs/reconstructed_state.csv, and VALIDATION_SUMMARY.md")
