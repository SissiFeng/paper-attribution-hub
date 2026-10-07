"""Read classification-neutral paper text from the imported Markdown API."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import quote

import httpx

from app.domain_adaptation.models import (
    PilotSelectionItem,
    PilotSelectionManifest,
    SourceChunk,
    SourcePaper,
    resolve_evidence_scope,
)


def load_pilot_selection(path: str | Path) -> PilotSelectionManifest:
    manifest = PilotSelectionManifest.model_validate_json(Path(path).read_text())
    paper_ids = [item.paper_id for item in manifest.papers]
    if len(set(paper_ids)) != len(paper_ids):
        raise ValueError("Pilot selection contains duplicate paper IDs")
    return manifest


def _metadata_index(client: httpx.Client, base_url: str) -> dict[str, dict]:
    records: list[dict] = []
    offset = 0
    while True:
        response = client.get(
            f"{base_url.rstrip('/')}/papers",
            params={"limit": 500, "offset": offset},
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Imported paper metadata response must be a list")
        records.extend(record for record in page if isinstance(record, dict))
        if len(page) < 500:
            break
        offset += len(page)
    return {
        record["id"]: record
        for record in records
        if isinstance(record.get("id"), str)
    }


def _section_type(title: str | None) -> str:
    normalized = (title or "").strip().casefold()
    if "reference" in normalized:
        return "references"
    if "acknowledg" in normalized:
        return "acknowledgements"
    if "experimental" in normalized:
        return "experimental"
    if "material" in normalized and "method" in normalized:
        return "methods"
    if "method" in normalized:
        return "methods"
    if "computational" in normalized or "calculation detail" in normalized:
        return "computational details"
    if "result" in normalized:
        return "results"
    if "discussion" in normalized:
        return "discussion"
    if "conclusion" in normalized:
        return "conclusion"
    if "introduction" in normalized or normalized == "background":
        return "introduction"
    if "abstract" in normalized:
        return "abstract"
    return "unknown"


def _section_type_for_path(path: list[str]) -> str:
    for title in reversed(path):
        inferred = _section_type(title)
        if inferred != "unknown":
            return inferred
    return "unknown"


def split_markdown_document(markdown: str, paper_id: str) -> list[SourceChunk]:
    """Split Markdown by heading hierarchy and paragraph boundaries."""
    heading_matches = list(re.finditer(r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*$", markdown))
    heading_info: list[tuple[re.Match[str], str, list[str]]] = []
    heading_stack: list[str] = []
    for heading in heading_matches:
        level = len(heading.group(1))
        title = heading.group(2).strip()
        heading_stack = heading_stack[: level - 1]
        heading_stack.append(title)
        heading_info.append((heading, title, list(heading_stack)))
    document_title = (
        heading_info[0][1]
        if len(heading_info) > 1
        and len(heading_info[0][0].group(1)) == 1
        and len(heading_info[1][0].group(1)) > 1
        else None
    )

    sections: list[tuple[str | None, list[str], int, int]] = []
    if heading_matches and heading_matches[0].start() > 0:
        sections.append((None, [], 0, heading_matches[0].start()))
    if not heading_matches:
        sections.append((None, [], 0, len(markdown)))
    for index, (heading, title, path) in enumerate(heading_info):
        body_start = heading.end()
        body_end = (
            heading_info[index + 1][0].start()
            if index + 1 < len(heading_info)
            else len(markdown)
        )
        semantic_path = path[1:] if document_title and path[0] == document_title else path
        sections.append((title, semantic_path, body_start, body_end))

    chunks: list[SourceChunk] = []
    for title, section_path, body_start, body_end in sections:
        body = markdown[body_start:body_end]
        block_start = 0
        boundaries = list(re.finditer(r"\n[ \t]*\n+", body))
        for boundary in boundaries + [None]:
            block_end = boundary.start() if boundary is not None else len(body)
            raw = body[block_start:block_end]
            left_trim = len(raw) - len(raw.lstrip())
            text = raw.strip()
            if text:
                absolute_start = body_start + block_start + left_trim
                absolute_end = absolute_start + len(text)
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                chunk_id = "mdchk_" + hashlib.sha256(
                    (
                        f"{paper_id}\0{title or ''}\0{absolute_start}\0"
                        f"{absolute_end}\0{content_hash}"
                    ).encode("utf-8")
                ).hexdigest()[:16]
                chunks.append(
                    SourceChunk(
                        chunk_id=chunk_id,
                        section_type=_section_type_for_path(section_path),
                        section_title=title,
                        section_path=section_path,
                        text=text,
                        document_char_start=absolute_start,
                        document_char_end=absolute_end,
                    )
                )
            block_start = boundary.end() if boundary is not None else len(body)
    return chunks


class ImportedApiSource:
    """Load only bibliographic identity and Markdown-derived chunks.

    The upstream response also contains attribution classifications, authors,
    and affiliations. Those fields are deliberately not represented here.
    """

    def __init__(
        self,
        *,
        base_url: str,
        source_bucket: str,
        source_prefix: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.source_bucket = source_bucket
        self.source_prefix = source_prefix
        self.client = client or httpx.Client(timeout=60.0)

    def _paper_index(self) -> dict[str, dict]:
        return _metadata_index(self.client, self.base_url)

    def load(self, selection: list[PilotSelectionItem]) -> list[SourcePaper]:
        index = self._paper_index()
        papers: list[SourcePaper] = []
        for item in selection:
            metadata = index.get(item.paper_id)
            if metadata is None:
                raise KeyError(f"Selected paper is missing from imported API: {item.paper_id}")
            encoded_id = quote(item.paper_id, safe="")
            response = self.client.get(
                f"{self.base_url}/papers/{encoded_id}/chunks"
            )
            response.raise_for_status()
            chunks = [
                SourceChunk(
                    chunk_id=record["chunk_id"],
                    section_type=record.get("section_type") or "unknown",
                    section_title=record.get("section_title"),
                    text=record["text"],
                )
                for record in response.json()
            ]
            papers.append(
                SourcePaper(
                    paper_id=item.paper_id,
                    title=metadata["title"],
                    year=metadata.get("year"),
                    doi=metadata.get("doi"),
                    selection_tier=item.selection_tier,
                    evidence_scope=resolve_evidence_scope(
                        item.selection_tier, item.evidence_scope
                    ),
                    selection_reasons=item.selection_reasons,
                    task_split=item.task_split,
                    source_bucket=self.source_bucket,
                    source_prefix=self.source_prefix,
                    chunks=chunks,
                )
            )
        return papers


class S3MarkdownSource:
    """Read and verify original Markdown through Zotero document manifests."""

    def __init__(
        self,
        *,
        s3_client,
        metadata_client: httpx.Client,
        metadata_api_base: str,
        bucket: str,
        group_id: str,
        frozen_metadata: dict[str, dict] | None = None,
    ) -> None:
        self.s3_client = s3_client
        self.metadata_client = metadata_client
        self.metadata_api_base = metadata_api_base.rstrip("/")
        self.bucket = bucket
        self.group_id = str(group_id)
        self.raw_prefix = f"raw/zotero/group={self.group_id}/"
        self.manifest_prefix = f"manifests/zotero/group={self.group_id}/"
        self.frozen_metadata = frozen_metadata

    def _read_bytes(self, key: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            content = body.read()
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        if not isinstance(content, bytes):
            raise TypeError(f"S3 object body is not bytes: {key}")
        return content

    def _manifest_keys(self, selection: list[PilotSelectionItem]) -> list[str]:
        configured = [item.source_manifest_key for item in selection]
        if all(configured):
            configured_keys = sorted(str(key) for key in configured)
            if any(
                not key.startswith(self.manifest_prefix)
                or not key.endswith("/document-manifest.json")
                for key in configured_keys
            ):
                raise ValueError("Configured S3 manifest key is outside the source prefix")
            return configured_keys
        paginator = self.s3_client.get_paginator("list_objects_v2")
        listed_keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self.manifest_prefix):
            listed_keys.extend(
                str(item["Key"])
                for item in page.get("Contents") or []
                if str(item.get("Key") or "").endswith("/document-manifest.json")
            )
        return sorted(listed_keys)

    def _selected_manifests(
        self, selection: list[PilotSelectionItem]
    ) -> dict[str, tuple[str, dict]]:
        selected_ids = {item.paper_id for item in selection}
        candidates: dict[str, list[tuple[tuple[int, str, str], str, dict]]] = {}
        for key in self._manifest_keys(selection):
            try:
                payload = json.loads(self._read_bytes(key))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"Invalid S3 document manifest: {key}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"S3 document manifest must be an object: {key}")
            paper_id = str(payload.get("paper_id") or "")
            if paper_id not in selected_ids:
                continue
            if (
                payload.get("kind") != "zotero_markdown_document"
                or int(payload.get("schema_version") or 0) != 1
                or payload.get("status") != "ready"
            ):
                raise ValueError(f"Unsupported S3 document manifest: {key}")
            zotero = payload.get("zotero")
            markdown = payload.get("markdown")
            if not isinstance(zotero, dict) or not isinstance(markdown, dict):
                raise ValueError(f"Incomplete S3 document manifest: {key}")
            if str(zotero.get("group_id")) != self.group_id:
                raise ValueError(f"Unexpected Zotero group in manifest: {key}")
            markdown_key = str(markdown.get("key") or "")
            if (
                str(markdown.get("bucket") or "") != self.bucket
                or not markdown_key.startswith(self.raw_prefix)
                or not markdown_key.endswith("/document.md")
            ):
                raise ValueError(f"Invalid Markdown provenance in manifest: {key}")
            rank = (
                int(zotero.get("attachment_version") or 0),
                str(payload.get("created_at") or ""),
                key,
            )
            candidates.setdefault(paper_id, []).append((rank, key, payload))

        missing = sorted(selected_ids - candidates.keys())
        if missing:
            raise KeyError(
                "Selected papers are missing S3 Markdown manifests: "
                + ", ".join(missing)
            )
        return {
            paper_id: (key, payload)
            for paper_id, values in candidates.items()
            for _rank, key, payload in [max(values, key=lambda item: item[0])]
        }

    def load(self, selection: list[PilotSelectionItem]) -> list[SourcePaper]:
        metadata = self.frozen_metadata or _metadata_index(
            self.metadata_client, self.metadata_api_base
        )
        manifests = self._selected_manifests(selection)
        papers: list[SourcePaper] = []
        for item in selection:
            paper_metadata = metadata.get(item.paper_id)
            if paper_metadata is None:
                raise KeyError(f"Selected paper is missing metadata: {item.paper_id}")
            manifest_key, manifest = manifests[item.paper_id]
            markdown_metadata = manifest["markdown"]
            markdown_key = str(markdown_metadata["key"])
            markdown_bytes = self._read_bytes(markdown_key)
            actual_sha256 = hashlib.sha256(markdown_bytes).hexdigest()
            expected_sha256 = str(markdown_metadata.get("sha256") or "")
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    f"Markdown checksum does not match manifest: {markdown_key}"
                )
            try:
                markdown = markdown_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"Markdown is not UTF-8: {markdown_key}") from exc
            papers.append(
                SourcePaper(
                    paper_id=item.paper_id,
                    title=paper_metadata["title"],
                    year=paper_metadata.get("year"),
                    doi=paper_metadata.get("doi"),
                    selection_tier=item.selection_tier,
                    evidence_scope=resolve_evidence_scope(
                        item.selection_tier, item.evidence_scope
                    ),
                    selection_reasons=item.selection_reasons,
                    task_split=item.task_split,
                    source_bucket=self.bucket,
                    source_prefix=self.raw_prefix,
                    source_manifest_key=manifest_key,
                    source_markdown_key=markdown_key,
                    source_markdown_sha256=actual_sha256,
                    chunks=split_markdown_document(markdown, item.paper_id),
                )
            )
        return papers
