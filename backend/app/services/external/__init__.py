"""External-API clients for OpenAlex / Semantic Scholar / Crossref + cache."""

from app.services.external.base import ExternalClient, ExternalError
from app.services.external.cache import (
    cached_get,
    invalidate_cache,
    read_cache,
    write_cache,
)

__all__ = [
    "ExternalClient",
    "ExternalError",
    "cached_get",
    "invalidate_cache",
    "read_cache",
    "write_cache",
]
