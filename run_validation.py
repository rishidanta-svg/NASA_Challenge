"""One command to reproduce everything:  .venv/bin/python run_validation.py
Add --skip-download to reuse data/processed/ instead of re-fetching."""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
PY = sys.executable
skip = "--skip-download" in sys.argv
import os
if "--skip-png" in sys.argv:
    os.environ["SARS_SKIP_PNG"] = "1"
    print("PNG export skipped explicitly; existing PNGs are not refreshed. HTML plots and science products will be regenerated.")

steps = []
if not skip:
    steps += ["fetch_lidar_tide.py", "s2.py", "s1.py"]
    if os.getenv("NISAR_INPUT") or list(Path(os.getenv("NISAR_RAW_DIR", SRC.parent / "data/raw/nisar")).glob("*.h5")):
        steps.append("nisar.py")
    else:
        print("!! No local NISAR HDF5 input: acquisition processing skipped. "
              "Set NISAR_INPUT to a local GCOV file; committed processed inputs remain available.")
# Rebuild boundaries, score sensors, generate the Bayesian reconstruction,
# then create and independently check the report.
steps += [
    "audit_inputs.py",
    "time_gaps.py",
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
        if s == "selfcheck.py":
            # Record failed scientific checks in the final report even on a nonzero exit.
            subprocess.run([PY, "make_report.py"], cwd=SRC, check=True)
        sys.exit(f"step {s} failed; see outputs/self_checks.csv and VALIDATION_SUMMARY.md")
print("\nDone. See outputs/, outputs/reconstructed_state.csv, and VALIDATION_SUMMARY.md")
