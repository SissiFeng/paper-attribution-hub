"""Container entrypoint: prepare the DB and optionally sync Zotero, then serve.

Schema bootstrap and Zotero sync run as best-effort steps: a non-zero exit is
logged loudly but never prevents uvicorn from starting.  A running API whose
`/health` is green and whose `/debug/db` reports the real error is far more
useful during a demo than a container that never boots.

Usage (Docker CMD):
    python -m app.scripts.serve
"""

from __future__ import annotations

import os
import subprocess
import sys


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
    from app.config import settings

    if settings.zotero_sync_on_startup:
        zotero_args = [
            "app.scripts.sync_zotero",
            "--seed-if-empty",
            "--classify",
        ]
        if settings.zotero_download_fulltexts:
            zotero_args.append("--download-fulltexts")
        sync_exit = _run_step("Zotero corpus sync", zotero_args)
        if settings.sdl_stage1_only and sync_exit != 0:
            raise SystemExit(
                "SDL Stage 1 Zotero validation failed; refusing to serve a "
                "legacy or mixed corpus"
            )

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
