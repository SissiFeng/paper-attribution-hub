"""Generate a cross-SDL experiment-design proposal for a target SDL.

Matches transferable knowledge units (TKUs) from source domains against the
target's profile (data/sdl_targets.yaml), writes a markdown proposal into the
llm-wiki vault, and prints the path plus the match table.

Usage:
    python -m app.scripts.generate_transfer_design --target sdl4 --no-llm
    python -m app.scripts.generate_transfer_design --target sdl4 --source-domain battery --top-k 8
    python -m app.scripts.generate_transfer_design --target sdl4 --json
"""
from __future__ import annotations

import argparse
import json

from app.db import SessionLocal
from app.services.transfer_designer import export_transfer_md, generate_design


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="target SDL id, e.g. sdl4")
    parser.add_argument("--source-domain", default=None)
    parser.add_argument("--top-k", type=int, default=6)
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument("--llm", dest="llm", action="store_true")
    llm_group.add_argument("--no-llm", dest="llm", action="store_false")
    parser.set_defaults(llm=False)
    parser.add_argument("--json", action="store_true", help="print design JSON")
    args = parser.parse_args()

    with SessionLocal() as session:
        # When --no-llm, force template mode by passing a sentinel that
        # generate_design ignores; we simply skip provider resolution by
        # generating without a client and disabling provider lookup.
        if args.llm:
            design = generate_design(
                session, args.target, source_domain=args.source_domain, top_k=args.top_k
            )
        else:
            design = generate_design(
                session,
                args.target,
                source_domain=args.source_domain,
                llm_client=_NoLLM(),
                top_k=args.top_k,
            )
        path = export_transfer_md(
            session,
            args.target,
            source_domain=args.source_domain,
            llm_client=None if args.llm else _NoLLM(),
            top_k=args.top_k,
        )

    if args.json:
        print(json.dumps(design, ensure_ascii=False, indent=2))
        return

    print(f"Wrote transfer design to {path}  (mode: {design['mode']})")
    print(f"\nMatched {len(design['matches'])} source(s):")
    print(f"{'paper_id':<14} {'domain':<14} {'score':>5}  title")
    for m in design["matches"]:
        title = (m["title"][:60] + "…") if len(m["title"]) > 61 else m["title"]
        print(f"{m['paper_id']:<14} {m['source_domain']:<14} {m['score']:>5}  {title}")


class _NoLLM:
    """A client that always fails, so generate_design falls back to template."""

    def __call__(self, messages):  # pragma: no cover - trivial
        raise RuntimeError("LLM disabled (--no-llm)")


if __name__ == "__main__":
    main()
