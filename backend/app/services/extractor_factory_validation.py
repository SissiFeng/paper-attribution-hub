"""Schema and ontology validation for extractor-factory JSONL artifacts."""
from __future__ import annotations

import json
import math
from pathlib import Path


class StructuredArtifactError(ValueError):
    pass


_EXPECTED_NORMALIZATION_CONTRACT = {
    "research_strategy.problem_type": "research_goals",
    "research_strategy.strategy": "strategy_concepts",
    "research_strategy.decision": "decision_operators",
    "research_strategy.constraints": "context_conditions",
    "transferable_pattern.required_conditions": "context_conditions",
    "transferable_pattern.failure_conditions": "context_conditions",
    "evidence_spans.evidence_type": "evidence_types",
}


def audit_structured_records(
    records_path: Path,
    *,
    payload_field: str,
    schema_path: Path,
    ontology_path: Path,
) -> dict:
    schema = _read_object(schema_path)
    ontology = _read_object(ontology_path)
    errors: list[dict] = _ontology_contract_errors(ontology)
    rows = _read_jsonl(records_path)
    for line_number, row in enumerate(rows, start=1):
        payload = row.get(payload_field)
        if not isinstance(payload, dict):
            errors.append(
                {
                    "line": line_number,
                    "path": payload_field,
                    "message": "must be an object",
                }
            )
            continue
        for path, message in _validate_schema(payload, schema, schema, "$"):
            errors.append(
                {
                    "line": line_number,
                    "path": f"{payload_field}{path[1:]}",
                    "message": message,
                }
            )
        for path, layer, concept in _canonical_concepts(payload):
            allowed_concepts = ontology.get(layer)
            if not isinstance(allowed_concepts, list):
                errors.append(
                    {
                        "line": line_number,
                        "path": f"{payload_field}.{path}",
                        "message": f"unknown ontology layer '{layer}'",
                    }
                )
            elif concept not in allowed_concepts:
                errors.append(
                    {
                        "line": line_number,
                        "path": f"{payload_field}.{path}",
                        "message": (
                            f"unknown {layer} canonical_concept '{concept}'"
                        ),
                    }
                )
        errors.extend(
            _claim_grounding_errors(
                payload,
                line_number=line_number,
                payload_field=payload_field,
            )
        )
        errors.extend(
            _evidence_span_errors(
                row,
                payload,
                ontology=ontology,
                line_number=line_number,
                payload_field=payload_field,
            )
        )
    return {
        "passed": not errors,
        "records": len(rows),
        "payload_field": payload_field,
        "schema_id": schema.get("$id"),
        "ontology_id": ontology.get("ontology_id"),
        "errors": errors,
    }


def require_structured_records(
    records_path: Path,
    *,
    payload_field: str,
    schema_path: Path,
    ontology_path: Path,
) -> dict:
    report = audit_structured_records(
        records_path,
        payload_field=payload_field,
        schema_path=schema_path,
        ontology_path=ontology_path,
    )
    if not report["passed"]:
        first = report["errors"][0]
        raise StructuredArtifactError(
            f"{records_path.name}:{first['line']} {first['path']} "
            f"{first['message']}"
        )
    return report


def _validate_schema(value, schema: dict, root: dict, path: str):
    if "$ref" in schema:
        schema = _resolve_ref(root, schema["$ref"])
    if "enum" in schema and value not in schema["enum"]:
        yield path, f"must be one of {schema['enum']}"
        return

    allowed_types = schema.get("type")
    if allowed_types:
        allowed = (
            set(allowed_types)
            if isinstance(allowed_types, list)
            else {allowed_types}
        )
        if not _matches_type(value, allowed):
            yield path, f"must have type {sorted(allowed)}"
            return
    if value is None:
        return

    if isinstance(value, dict):
        required = schema.get("required") or []
        for name in required:
            if name not in value:
                yield f"{path}.{name}", "is required"
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    yield f"{path}.{name}", "is not allowed"
        for name, child in properties.items():
            if name in value:
                yield from _validate_schema(
                    value[name],
                    child,
                    root,
                    f"{path}.{name}",
                )
    elif isinstance(value, list) and isinstance(schema.get("items"), dict):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None and len(value) < minimum:
            yield path, f"must contain at least {minimum} items"
        if maximum is not None and len(value) > maximum:
            yield path, f"must contain at most {maximum} items"
        for index, item in enumerate(value):
            yield from _validate_schema(
                item,
                schema["items"],
                root,
                f"{path}[{index}]",
            )
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            yield path, "must be finite"
            return
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            yield path, f"must be >= {minimum}"
        if maximum is not None and value > maximum:
            yield path, f"must be <= {maximum}"


def _resolve_ref(root: dict, reference: str) -> dict:
    if not reference.startswith("#/"):
        raise StructuredArtifactError(
            f"Only local JSON Schema references are supported: {reference}"
        )
    value = root
    for part in reference[2:].split("/"):
        if not isinstance(value, dict) or part not in value:
            raise StructuredArtifactError(f"Unknown JSON Schema reference: {reference}")
        value = value[part]
    if not isinstance(value, dict):
        raise StructuredArtifactError(f"JSON Schema reference is not an object: {reference}")
    return value


def _matches_type(value, allowed: set[str]) -> bool:
    if value is None:
        return "null" in allowed
    if isinstance(value, bool):
        return "boolean" in allowed
    if isinstance(value, str):
        return "string" in allowed
    if isinstance(value, int):
        return "integer" in allowed or "number" in allowed
    if isinstance(value, float):
        return "number" in allowed
    if isinstance(value, dict):
        return "object" in allowed
    if isinstance(value, list):
        return "array" in allowed
    return False


def _canonical_concepts(value, path: str = ""):
    if isinstance(value, dict):
        if "canonical_concept" in value and value["canonical_concept"] is not None:
            layer = value.get("ontology_layer")
            yield (
                f"{path}.canonical_concept".lstrip("."),
                str(layer),
                str(value["canonical_concept"]),
            )
        for name, child in value.items():
            yield from _canonical_concepts(child, f"{path}.{name}".lstrip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _canonical_concepts(child, f"{path}[{index}]")


def _claim_grounding_errors(
    payload: dict,
    *,
    line_number: int,
    payload_field: str,
) -> list[dict]:
    errors = []
    for path, claim in _grounded_claims(payload):
        spans = claim.get("evidence_spans")
        asserted = any(
            claim.get(name) is not None
            for name in ("value", "canonical_concept", "surface_form")
        )
        if asserted and not spans:
            errors.append(
                {
                    "line": line_number,
                    "path": f"{payload_field}.{path}.evidence_spans",
                    "message": "a non-null claim requires at least one evidence span",
                }
            )
        surface_form = claim.get("surface_form")
        if (
            isinstance(surface_form, str)
            and surface_form.strip()
            and isinstance(spans, list)
            and spans
            and not any(
                isinstance(span, dict)
                and isinstance(span.get("text_span"), str)
                and _normalized_text(surface_form)
                in _normalized_text(span["text_span"])
                for span in spans
            )
        ):
            errors.append(
                {
                    "line": line_number,
                    "path": f"{payload_field}.{path}.surface_form",
                    "message": "surface_form is not bound to a cited evidence span",
                }
            )
        if not asserted and spans:
            errors.append(
                {
                    "line": line_number,
                    "path": f"{payload_field}.{path}.evidence_spans",
                    "message": "a null claim must not cite evidence spans",
                }
            )
    return errors


def _grounded_claims(value, path: str = ""):
    if isinstance(value, dict):
        if "evidence_spans" in value:
            yield path, value
        for name, child in value.items():
            if name != "evidence_spans":
                yield from _grounded_claims(
                    child,
                    f"{path}.{name}".lstrip("."),
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _grounded_claims(child, f"{path}[{index}]")


def _evidence_span_errors(
    row: dict,
    payload: dict,
    *,
    ontology: dict,
    line_number: int,
    payload_field: str,
) -> list[dict]:
    paper_id = row.get("paper_id")
    chunk_id = row.get("chunk_id")
    input_text = row.get("input_text")
    context_chunks = row.get("context_chunks") or {}
    chunk_text = (
        {str(chunk_id): input_text}
        if isinstance(chunk_id, str) and isinstance(input_text, str)
        else {}
    )
    if isinstance(context_chunks, dict):
        chunk_text.update(
            {
                str(key): value
                for key, value in context_chunks.items()
                if isinstance(value, str)
            }
        )

    errors = []
    for path, span in _evidence_spans(payload):
        span_chunk_id = span.get("chunk_id")
        source_text = chunk_text.get(str(span_chunk_id))
        start = span.get("start_offset")
        end = span.get("end_offset")
        text_span = span.get("text_span")
        evidence_type = span.get("evidence_type")
        allowed_evidence_types = ontology.get("evidence_types")
        message = None
        if not isinstance(allowed_evidence_types, list):
            message = "ontology does not define evidence_types"
        elif evidence_type not in allowed_evidence_types:
            message = f"unknown evidence_type '{evidence_type}'"
        elif span.get("paper_id") != paper_id:
            message = "paper_id does not match the record"
        elif source_text is None:
            message = "chunk_id is not present in the record context"
        elif (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(source_text)
        ):
            message = "offsets are outside the cited chunk"
        elif not isinstance(text_span, str) or not text_span:
            message = "text_span must be non-empty"
        elif source_text[start:end] != text_span:
            message = "text_span does not match the cited offsets"
        if message:
            errors.append(
                {
                    "line": line_number,
                    "path": f"{payload_field}.{path}",
                    "message": message,
                }
            )
    return errors


def _ontology_contract_errors(ontology: dict) -> list[dict]:
    contract = ontology.get("normalization_contract")
    if contract is None:
        return [
            {
                "line": 0,
                "path": "ontology.normalization_contract",
                "message": "is required",
            }
        ]
    errors = []
    if not isinstance(contract, dict):
        return [
            {
                "line": 0,
                "path": "ontology.normalization_contract",
                "message": "must be an object",
            }
        ]
    unexpected_paths = sorted(
        set(contract) - set(_EXPECTED_NORMALIZATION_CONTRACT)
    )
    for path in unexpected_paths:
        errors.append(
            {
                "line": 0,
                "path": f"ontology.normalization_contract.{path}",
                "message": "is not a supported normalized output path",
            }
        )
    for path, expected_layer in _EXPECTED_NORMALIZATION_CONTRACT.items():
        if contract.get(path) != expected_layer:
            errors.append(
                {
                    "line": 0,
                    "path": f"ontology.normalization_contract.{path}",
                    "message": (
                        f"must map to ontology layer '{expected_layer}'"
                    ),
                }
            )
    for expected_layer in sorted(set(_EXPECTED_NORMALIZATION_CONTRACT.values())):
        concepts = ontology.get(expected_layer)
        if (
            not isinstance(concepts, list)
            or not concepts
            or any(
                not isinstance(value, str) or not value.strip()
                for value in concepts
            )
            or len(set(concepts)) != len(concepts)
        ):
            errors.append(
                {
                    "line": 0,
                    "path": f"ontology.{expected_layer}",
                    "message": "must be a non-empty unique string list",
                }
            )
    return errors


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().split())


def _evidence_spans(value, path: str = ""):
    if isinstance(value, dict):
        spans = value.get("evidence_spans")
        if isinstance(spans, list):
            for index, span in enumerate(spans):
                if isinstance(span, dict):
                    yield (
                        f"{path}.evidence_spans[{index}]".lstrip("."),
                        span,
                    )
        for name, child in value.items():
            if name != "evidence_spans":
                yield from _evidence_spans(
                    child,
                    f"{path}.{name}".lstrip("."),
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _evidence_spans(child, f"{path}[{index}]")


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StructuredArtifactError(f"{path} must contain a JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise StructuredArtifactError(
                f"{path}:{line_number} must contain a JSON object"
            )
        rows.append(value)
    return rows
