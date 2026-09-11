from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTEST = ["python3", "-m", "pytest", str(ROOT / "tests"), "-q"]
