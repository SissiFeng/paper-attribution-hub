from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_here = Path(__file__).resolve()
REPO_ROOT = _here.parents[2]
DATA_DIR = REPO_ROOT / "data"
BACKEND_ROOT = REPO_ROOT / "backend"
# In Docker /backend doesn't exist; fall back to /tmp so SQLite can be created.
_SQLITE_DIR = BACKEND_ROOT if BACKEND_ROOT.exists() else Path("/tmp")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAS_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{_SQLITE_DIR / 'paper_attribution.db'}"

    papers_csv: Path = DATA_DIR / "sample_papers.csv"
    people_csv: Path = DATA_DIR / "ac_members.csv"
    institutions_csv: Path = DATA_DIR / "institution_aliases.csv"
    topics_yaml: Path = DATA_DIR / "topic_taxonomy.yaml"
    fulltexts_dir: Path = DATA_DIR / "fulltexts"
    eval_labels_csv: Path = DATA_DIR / "eval_labels.csv"
    ac_core_papers_csv: Path = DATA_DIR / "ac_core_papers.csv"

    fuzzy_author_threshold: float = 0.85
    fuzzy_institution_threshold: float = 0.85

    # v0.1 blend (still used when no full text is available)
    author_weight: float = 0.40
    institution_weight: float = 0.20
    topic_weight: float = 0.30
    network_weight: float = 0.10

    # v0.2 blend (used when fulltext_evidence_score > 0)
    fulltext_evidence_weight: float = 0.20
    author_weight_fulltext: float = 0.35
    institution_weight_fulltext: float = 0.15
    topic_weight_fulltext: float = 0.25
    network_weight_fulltext: float = 0.05

    # Full-text evidence floor: if the acknowledgement names AC funding, the
    # label cannot drop below RELATED_RELEVANT regardless of author match.
    funding_evidence_floor_score: float = 0.5

    # v0.3 graph signals
    citation_weight: float = 0.10  # weight in confidence blend when present
    network_weight_v3: float = 0.10  # second-degree collaborator weight
    second_degree_floor_score: float = 0.55  # min confidence when only second-degree

    # v0.4 advanced digest
    # GROBID HTTP service URL. Empty disables GROBID and forces PyMuPDF.
    grobid_url: str = ""
    grobid_timeout_s: float = 60.0
    # Apply contextual chunk prefixing before BM25 / embedding (Anthropic style).
    contextual_chunking: bool = True
    # Reranker: "none" (default) or "cross-encoder" (requires sentence-transformers).
    reranker_backend: str = "none"
    domain_vocabulary_yaml: Path = DATA_DIR / "domain_vocabulary.yaml"

    # v0.5 external data sources (overridable via PAS_* env vars)
    openalex_url: str = "https://api.openalex.org"
    openalex_mailto: str = ""
    semantic_scholar_url: str = "https://api.semanticscholar.org/graph/v1"
    semantic_scholar_api_key: str = ""
    crossref_url: str = "https://api.crossref.org"
    external_cache_ttl_hours: int = 24 * 7  # one week
    # Hybrid auto/queue split (see docs/discovery_design.md).
    discovery_auto_cite_threshold: int = 2
    discovery_max_candidates_per_strategy: int = 50

    # LLM / API keys
    anthropic_api_key: str = ""
    # Kimi (MoonShot AI) — OpenAI-compatible, set PAS_KIMI_API_KEY in Render
    kimi_api_key: str = ""
    kimi_model: str = "moonshot-v1-32k"
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    # Which LLM to use for answer generation: "kimi" | "anthropic" | "auto"
    # "auto" = use kimi if key set, else anthropic, else retrieval-only
    llm_provider: str = "auto"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://frontend-delta-three-38.vercel.app",
    ]


settings = Settings()
