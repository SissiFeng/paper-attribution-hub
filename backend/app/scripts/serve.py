"""Latency-safe container entrypoint: start the API immediately.

Database bootstrap runs in Render's pre-deploy phase. Corpus and knowledge-base
seeding are explicit operations, not web-process startup work. This keeps an
instance restart from extending an outage while migrations or ingestion run.

Usage (Docker CMD):
    python -m app.scripts.serve
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    port = os.environ.get("PORT", "8000")
    print(f"[serve] starting uvicorn on :{port}", flush=True)
    # exec so uvicorn replaces this process and receives container signals.
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
