from pathlib import Path
import sys

# Optional PAS integration tests use this checkout's backend runtime.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_monitor import env as env  # noqa: E402
