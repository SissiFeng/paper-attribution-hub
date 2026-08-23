"""Standalone metadata-only API for institution comparison."""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.api import institution_authorship


app = FastAPI(
    title="Institution Comparison API",
    version=__version__,
    description=(
        "Read-only institution comparison computed from a pinned immutable "
        "selected Tier 1 or Tier 1 + Tier 2 metadata snapshot in S3."
    ),
)

# CloudFront removes the public ``/api`` prefix before forwarding to the ALB.
# Keep the prefixed form too so direct ALB and container smoke tests exercise
# the same application without depending on that edge rewrite.
app.include_router(institution_authorship.router)
app.include_router(
    institution_authorship.router,
    prefix="/api",
    include_in_schema=False,
)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "institution-comparison",
        "data_source": "s3-metadata-snapshot",
        "version": __version__,
    }
