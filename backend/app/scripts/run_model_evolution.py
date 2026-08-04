"""Run durable human-feedback reconciliation and pending model batches once."""

from __future__ import annotations

import argparse
import json
import sys

from app.db import SessionLocal, init_database
from app.logging_utils import configure_logging
from app.services.model_evolution import (
    model_evolution_status,
    reconcile_training_feedback,
    run_pending_model_evolution,
    training_run_to_dict,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    configure_logging()
    init_database()
    with SessionLocal() as session:
        reconciled = reconcile_training_feedback(session)
        runs = run_pending_model_evolution(session)
        status = model_evolution_status(session)

    payload = {
        "reconciled_feedback": reconciled,
        "training_runs": [training_run_to_dict(run) for run in runs],
        "status": status,
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(
            "model evolution: "
            f"reconciled={reconciled} runs={len(runs)} "
            f"pending={status['pending_reviews']}"
        )
    return 1 if any(run.status == "FAILED" for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
