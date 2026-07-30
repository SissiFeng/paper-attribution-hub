"""Demo-safe container entrypoint: prepare DB and demo knowledge, then serve.

Schema bootstrap and data/lab seeding run before the API. Version-gated entity
extraction then runs in a daemon thread with per-batch commits, so health checks
do not wait for a corpus scan and interrupted work resumes on the next boot.
Every preparation step is best-effort: a non-zero exit is logged loudly but
never prevents uvicorn from starting.

Usage (Docker CMD):
    python -m app.scripts.serve
"""

from __future__ import annotations

import os
import subprocess
import sys
from threading import Thread


def _run_step(name: str, module_args: list[str]) -> int:
    """Run ``python -m <module_args>`` as a subprocess, never raising.

    Returns the child's exit code; logs a warning on failure and continues.
    """
    print(f"[serve] {name}...", flush=True)
    result = subprocess.run([sys.executable, "-m", *module_args])
    if result.returncode != 0:
        print(
            f"[serve] WARNING: {name} exited {result.returncode}; "
            "starting the API anyway.",
            file=sys.stderr,
            flush=True,
        )
    return result.returncode


def main() -> None:
    _run_step("database bootstrap", ["app.scripts.db_bootstrap"])
    _run_step(
        "database seed",
        [
            "app.scripts.ingest_scopus_batch",
            "--seed-if-under",
            "1000",
            "--prune-non-real",
        ],
    )
    _run_step("SDL lab seed", ["app.scripts.seed_sdl_labs", "--json"])
    extraction = Thread(
        target=_run_step,
        args=(
            "versioned entity extraction",
            [
                "app.scripts.run_entity_extraction",
                "--if-stale-version",
                "--json",
            ],
        ),
        daemon=True,
        name="entity-extraction-backfill",
    )
    extraction.start()

    port = os.environ.get("PORT", "8000")
    print(f"[serve] starting uvicorn on :{port}", flush=True)
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(port),
    )


if __name__ == "__main__":
    main()
