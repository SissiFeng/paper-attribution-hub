"""Audit tokenizer fragmentation on an exported scientific corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.entity_extractor import load_sdl_entities
from app.services.tokenizer_fragmentation import (
    DomainRetrievalTokenizerAdapter,
    HuggingFaceTokenizerAdapter,
    WhitespaceTokenizerAdapter,
    audit_tokenizer_fragmentation,
)


def _load_texts(path: Path, limit: int | None) -> list[str]:
    texts: list[str] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            texts.append(str(json.loads(line)["text"]))
            if limit is not None and len(texts) >= limit:
                break
    return texts


def _domain_terms() -> list[str]:
    vocabulary = load_sdl_entities()
    return sorted(
        {
            canonical
            for entity_type in ("method", "material", "instrument", "software")
            for canonical in vocabulary.get(entity_type, {}).values()
        },
        key=str.casefold,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--tokenizer",
        choices=("whitespace", "domain-retrieval", "huggingface"),
        default="whitespace",
    )
    parser.add_argument("--model", help="Hugging Face model name or local path.")
    parser.add_argument(
        "--allow-download",
        action="store_true",
        help="Allow Hugging Face to download tokenizer files.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.tokenizer == "huggingface" and not args.model:
        parser.error("--model is required for the Hugging Face tokenizer")

    if args.tokenizer == "domain-retrieval":
        tokenizer = DomainRetrievalTokenizerAdapter()
    elif args.tokenizer == "huggingface":
        tokenizer = HuggingFaceTokenizerAdapter(
            args.model,
            local_files_only=not args.allow_download,
        )
    else:
        tokenizer = WhitespaceTokenizerAdapter()
    report = audit_tokenizer_fragmentation(
        texts=_load_texts(args.corpus, args.limit),
        domain_terms=_domain_terms(),
        tokenizer=tokenizer,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
