"""Run current security acceptance tests. Historical pre-fix evidence is in docs/evaluation/security-review-probes.json."""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests/test_security.py"], cwd=root / "apps/api"))
