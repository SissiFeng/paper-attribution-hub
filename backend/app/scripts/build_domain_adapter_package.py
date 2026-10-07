"""Build one versioned, classification-neutral scientific domain package.

Examples:

    python -m app.scripts.build_domain_adapter_package --extractor heuristic

    python -m app.scripts.build_domain_adapter_package \
        --extractor bedrock \
        --aws-profile pas-sdl0-dev \
        --model-id us.anthropic.claude-sonnet-4-6

    python -m app.scripts.build_domain_adapter_package \
        --extractor bedrock \
        --aws-profile pas-sdl0-dev \
        --teacher-region us-east-1 \
        --model-id moonshotai.kimi-k2.5
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx

from app.domain_adaptation.builder import build_domain_adapter_package
from app.domain_adaptation.chunking import ScientificChunkingPolicy
from app.domain_adaptation.extractors import HeuristicOerExtractor
from app.domain_adaptation.models import DomainPackageConfig
from app.domain_adaptation.models import PilotSelectionItem
from app.domain_adaptation.models import PilotSelectionManifest
from app.domain_adaptation.source import (
    ImportedApiSource,
    S3MarkdownSource,
    load_pilot_selection,
)
from app.domain_adaptation.teacher import (
    BEDROCK_TEACHER_PROMPT_VERSION,
    BedrockTeacherExtractor,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SELECTION = (
    PROJECT_ROOT / "data/domain_adapters/oer_electrocatalysis_pilot.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "outputs/domain-adapters/oer-electrocatalysis/0.1.0-pilot"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a classification-neutral domain package from imported "
            "S3 Markdown chunks."
        )
    )
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--package-version",
        default=None,
        help="Override the selection manifest version for a new package build.",
    )
    parser.add_argument(
        "--task-split",
        choices=("all", "train", "evaluation"),
        default="all",
        help=(
            "Build all selected papers or one frozen task split. The evaluation "
            "slice is useful for low-cost, same-paper teacher benchmarks."
        ),
    )
    parser.add_argument(
        "--api-base",
        default="https://d1ai8ldqsh81fz.cloudfront.net/api",
    )
    parser.add_argument(
        "--source-bucket",
        default="paper-attribution-artifacts-dev-247893369214",
    )
    parser.add_argument(
        "--source-prefix",
        default="raw/zotero/group=6631056/",
    )
    parser.add_argument("--group-id", default="6631056")
    parser.add_argument(
        "--source-metadata-manifest",
        type=Path,
        default=None,
        help=(
            "Frozen package source/selection_manifest.json. When supplied, S3 "
            "builds do not depend on the live paper metadata API."
        ),
    )
    parser.add_argument(
        "--source",
        choices=("s3", "imported-api"),
        default="s3",
    )
    parser.add_argument(
        "--extractor",
        choices=("bedrock", "heuristic"),
        default="bedrock",
    )
    parser.add_argument(
        "--aws-profile",
        default=os.getenv("AWS_PROFILE", "pas-sdl0-dev"),
    )
    parser.add_argument("--aws-region", default="ca-central-1")
    parser.add_argument(
        "--teacher-region",
        default=os.getenv("AWS_BEDROCK_REGION", "ca-central-1"),
        help="Bedrock Runtime region; independent from the S3 source region.",
    )
    parser.add_argument(
        "--model-id",
        default="us.anthropic.claude-sonnet-4-6",
    )
    parser.add_argument(
        "--teacher-prompt-version",
        default=None,
        help=(
            "Recorded prompt/selection profile version. Non-OER packages "
            "default to scientific-protocol-teacher-v0.3."
        ),
    )
    parser.add_argument(
        "--domain-term",
        action="append",
        default=None,
        help=(
            "Domain term used only to rank bounded teacher context. Repeat for "
            "multiple terms; values are recorded in the package manifest."
        ),
    )
    parser.add_argument(
        "--teacher-min-chunk-score",
        type=int,
        default=None,
        help=(
            "Minimum deterministic context-ranking score. Defaults to 4 for "
            "the legacy OER profile and 2 for cross-domain scientific profiles."
        ),
    )
    parser.add_argument(
        "--teacher-scope-aware",
        action="store_true",
        help=(
            "Include paper-level primary/secondary scope and a conservative "
            "secondary-protocol abstention rule in the teacher prompt."
        ),
    )
    parser.add_argument(
        "--bedrock-read-timeout",
        type=int,
        default=300,
        help="Seconds to wait for one long-running Bedrock response.",
    )
    parser.add_argument(
        "--bedrock-max-attempts",
        type=int,
        default=4,
        help="Total SDK attempts for retryable Bedrock failures.",
    )
    parser.add_argument(
        "--bedrock-max-output-tokens",
        type=int,
        default=14000,
        help="Maximum tokens for one structured teacher response.",
    )
    parser.add_argument(
        "--teacher-cache-dir",
        type=Path,
        default=None,
        help="Per-paper Bedrock response cache; defaults inside the output directory.",
    )
    parser.add_argument(
        "--scientific-chunk-max-chars",
        type=int,
        default=6000,
        help=(
            "Safety limit after section and semantic boundaries; this is not "
            "the primary chunking rule."
        ),
    )
    parser.add_argument(
        "--scientific-chunk-min-merge-chars",
        type=int,
        default=800,
        help="Merge short adjacent scientific blocks within one section.",
    )
    return parser.parse_args()


def select_selection_items(
    selection: PilotSelectionManifest,
    task_split: str,
) -> list[PilotSelectionItem]:
    if task_split == "all":
        return selection.papers
    return [
        item for item in selection.papers if item.task_split == task_split
    ]


def _extractor(
    args: argparse.Namespace,
    selection: PilotSelectionManifest,
):
    if args.extractor == "heuristic":
        if selection.package_id != "oer-electrocatalysis":
            raise ValueError(
                "The deterministic heuristic baseline is OER-specific; use "
                "the evidence-bound teacher for other domains."
            )
        return HeuristicOerExtractor()

    import boto3  # type: ignore[import-untyped]
    from botocore.config import Config  # type: ignore[import-untyped]

    session = boto3.Session(profile_name=args.aws_profile)
    client = session.client(
        "bedrock-runtime",
        region_name=args.teacher_region,
        config=Config(
            connect_timeout=10,
            read_timeout=args.bedrock_read_timeout,
            retries={
                "total_max_attempts": args.bedrock_max_attempts,
                "mode": "standard",
            },
        ),
    )
    domain_terms = tuple(args.domain_term or ())
    if selection.package_id == "oer-electrocatalysis" and not domain_terms:
        domain_terms = ("OER", "oxygen evolution", "water oxidation")
    if selection.package_id != "oer-electrocatalysis" and not domain_terms:
        raise ValueError(
            "Non-OER teacher builds require at least one explicit --domain-term."
        )
    prompt_version = args.teacher_prompt_version or BEDROCK_TEACHER_PROMPT_VERSION
    minimum_chunk_score = args.teacher_min_chunk_score
    if minimum_chunk_score is None:
        minimum_chunk_score = (
            4 if selection.package_id == "oer-electrocatalysis" else 2
        )
    return BedrockTeacherExtractor(
        client=client,
        model_id=args.model_id,
        region=args.teacher_region,
        max_output_tokens=args.bedrock_max_output_tokens,
        cache_dir=args.teacher_cache_dir or args.output / ".teacher-cache",
        prompt_version=prompt_version,
        domain_terms=domain_terms,
        minimum_chunk_score=minimum_chunk_score,
        scope_aware=args.teacher_scope_aware,
    )


def _source(args: argparse.Namespace):
    if args.source == "imported-api":
        return ImportedApiSource(
            base_url=args.api_base,
            source_bucket=args.source_bucket,
            source_prefix=args.source_prefix,
        )

    import boto3  # type: ignore[import-untyped]

    session = boto3.Session(profile_name=args.aws_profile)
    frozen_metadata = None
    if args.source_metadata_manifest is not None:
        payload = json.loads(
            args.source_metadata_manifest.read_text(encoding="utf-8")
        )
        frozen_metadata = {
            str(record["paper_id"]): {
                "title": record["title"],
                "year": record.get("year"),
                "doi": record.get("doi"),
            }
            for record in payload.get("papers", [])
        }
    return S3MarkdownSource(
        s3_client=session.client("s3", region_name=args.aws_region),
        metadata_client=httpx.Client(timeout=60.0),
        metadata_api_base=args.api_base,
        bucket=args.source_bucket,
        group_id=args.group_id,
        frozen_metadata=frozen_metadata,
    )


def main() -> int:
    args = parse_args()
    selection = load_pilot_selection(args.selection)
    source = _source(args)
    papers = source.load(select_selection_items(selection, args.task_split))
    result = build_domain_adapter_package(
        papers=papers,
        output_dir=args.output,
        extractor=_extractor(args, selection),
        config=DomainPackageConfig(
            package_id=selection.package_id,
            package_version=args.package_version or selection.package_version,
            domain=selection.domain,
            source_access="s3_markdown"
            if args.source == "s3"
            else "imported_api",
        ),
        chunking_policy=ScientificChunkingPolicy(
            max_chars=args.scientific_chunk_max_chars,
            min_merge_chars=args.scientific_chunk_min_merge_chars,
        ),
    )
    print(
        json.dumps(
            {
                "output_dir": result.output_dir,
                "changed_files": result.changed_files,
                "extraction": result.manifest["extraction"],
                "counts": result.manifest["counts"],
                "validation": result.manifest["validation"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
