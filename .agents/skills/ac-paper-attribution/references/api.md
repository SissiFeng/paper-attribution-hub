# Attribution Skill API

Base path: `/api/v1/attribution-skills`

## Discover handlers

`GET /api/v1/attribution-skills` returns the contract, Skill, and policy
versions plus the five supported read-only handler names.

## Invoke

`POST /api/v1/attribution-skills/invoke`

```json
{
  "invocation_id": "caller-stable-nonce",
  "skill_name": "determine_ac_paper_attribution",
  "paper_id": "P001",
  "invocation_reason": "Determine AC attribution for the strategy review.",
  "policy_version": "ac-attribution-policy-v0.1",
  "budget": {
    "max_wall_seconds": 10,
    "max_retrieval_api_calls": 0,
    "max_model_calls": 0,
    "max_input_tokens": 0,
    "max_estimated_cost_usd": 0
  }
}
```

`policy_version` and `budget` are optional. The server rejects unsupported
policy versions instead of relabeling current logic with a caller-provided
version. `invocation_id` accepts only URL-safe letters, digits, `.`, `_`, `~`,
and `-`, so every accepted nonce is replayable through the documented path.
The current runtime is local and deterministic: it performs no retrieval API
or model calls.

The response is `AttributionSkillInvocation`. Important fields:

- `status`: `succeeded`, `review_required`, `failed`, or `budget_exhausted`
- `input_snapshot_id` and `input_content_hash`: server-owned input lineage
- `output_packet.evidence`: auditable supporting and contradicting records
- `output_packet.decision`: attribution decision and independent relevance label
- `skill_outcome`: handler-specific typed identity, membership, evidence,
  disagreement, or attribution result
- `cost`: measured calls, tokens, wall/extraction time, and review cost
- `resolution_path`: executed policy stages
- `failure`: structured stage/category when execution fails closed

The server persists the exact request, input snapshot, and validated response.
Reusing an `invocation_id` with the identical request replays the stored result.
Reusing it with any changed request returns HTTP 409.

## Replay

`GET /api/v1/attribution-skills/invocations/{invocation_id}`

This returns the exact validated invocation envelope stored by the original
call. When `PAS_API_KEY` is configured, replay requires the same `X-API-Key`
header as invoke. HTTP 404 means that invocation was never recorded.

## HTTP outcomes

- `200`: invocation executed or replayed; inspect the body status
- `401`: configured API key is missing or invalid
- `404`: paper or invocation does not exist
- `409`: nonce reuse with a different request
- `422`: request violates the typed contract
