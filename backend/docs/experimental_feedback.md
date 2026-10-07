# Experimental Feedback Packages

Experimental feedback is compiled into an immutable evidence package before it
can update a domain package or become a promotion candidate. Compilation does
not infer causality or apply claim updates.

## Minimum input

Each experiment run must provide:

- a stable run ID and domain;
- the protocol ID and exact domain-package version used;
- a timezone-aware execution timestamp;
- a source URI and SHA-256 digest of the raw result artifact;
- run status (`completed`, `failed`, or `invalid`);
- experimental conditions and instrument IDs when available;
- measurements for completed runs; and
- a failure reason for failed or invalid runs.

Measurements preserve the reported surface value. A normalized numeric value
and unit are optional, but they must be supplied together. Uncertainty is
optional and refers to the normalized value.

See
`data/domain_adapters/experimental_feedback_input.example.json` for a valid
input document.

## Compile

From the `backend` directory:

```bash
python -m app.scripts.compile_experimental_feedback \
  --input ../data/domain_adapters/experimental_feedback_input.example.json \
  --output ../outputs/domain-adapters/experimental-feedback/example.json
```

Repeated compilation of identical input produces the same content hash and
does not rewrite an unchanged output file.

## Evidence boundary

The compiler emits measurement and run-failure records. An LLM may propose a
claim update (`supports`, `refutes`, `refines`, or `invalidates`), but every
proposal must resolve to evidence records in the compiled package. A valid
reference does not make the interpretation true and does not promote it.

A domain feedback release is represented as a new domain-package version that
depends on both the previous domain version and the immutable evidence package.
The previous release is never mutated.

Experimental-feedback promotion additionally requires evidence-conditioned
belief-update evaluation. The evaluation observes whether a system correctly
chooses `revise`, `retain`, or `abstain`; it does not inspect hidden
chain-of-thought.
