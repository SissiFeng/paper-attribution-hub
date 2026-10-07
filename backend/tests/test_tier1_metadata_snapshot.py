from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from app.models import (
    Author,
    Institution,
    MetadataEnrichmentRun,
    Paper,
    PaperAuthorshipMetadata,
)
from app.services.tier1_metadata_snapshot import (
    build_author_institution_map_csv,
    build_tier1_metadata_snapshot,
    upload_tier1_metadata_snapshot,
)


def _write_source(tmp_path):
    source = tmp_path / "tier1.csv"
    source.write_text(
        "Key,Title,DOI,Author,Publication Year,Publication Title,Abstract Note,Url,Item Type,File Attachments\n"
        'k1,Test Paper,10.1000/test,"First A; Last B",2025,Test Journal,,,journalArticle,\n',
        encoding="utf-8",
    )
    return source


def _seed(session, source) -> None:
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    run_id = "meta_test"
    session.add(
        MetadataEnrichmentRun(
            id=run_id,
            agent_version="tier1_metadata_agent.v1",
            status="succeeded",
            input_path=str(source),
            input_sha256=source_sha256,
            configuration={},
            summary={"raw_rows": 1, "unique_dois": 1},
            errors=[],
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
    )
    session.add_all(
        [
            Institution(
                id="uoft",
                canonical_name="University of Toronto",
                aliases=[],
                normalized_aliases=["university of toronto"],
                country="CA",
                raw_metadata={"ror": "https://ror.org/03dbr7087"},
            ),
            Institution(
                id="oxford",
                canonical_name="University of Oxford",
                aliases=[],
                normalized_aliases=["university of oxford"],
                country="GB",
                raw_metadata={"ror": "https://ror.org/052gg0110"},
            ),
            Author(
                id="a1",
                canonical_name="First A",
                aliases=[],
                normalized_name="first a",
                raw_metadata={},
            ),
            Author(
                id="a2",
                canonical_name="Last B",
                aliases=[],
                normalized_name="last b",
                raw_metadata={},
            ),
            Paper(
                id="p1",
                title="Test Paper",
                doi="10.1000/test",
                year=2025,
                raw_metadata={
                    "tier1_metadata_agent": {
                        "run_id": run_id,
                        "input_sha256": source_sha256,
                        "quality_flags": [],
                        "openalex": {"id": "https://openalex.org/W1"},
                        "crossref": None,
                    }
                },
            ),
        ]
    )
    session.flush()
    uoft = {
        "institution_id": "uoft",
        "display_name": "University of Toronto",
        "ror": "https://ror.org/03dbr7087",
        "openalex_id": "https://openalex.org/I185261750",
        "country_code": "CA",
        "source": "openalex",
        "confidence": 0.98,
        "resolved": True,
    }
    oxford = {
        "institution_id": "oxford",
        "display_name": "University of Oxford",
        "ror": "https://ror.org/052gg0110",
        "openalex_id": "https://openalex.org/I40120149",
        "country_code": "GB",
        "source": "openalex",
        "confidence": 0.98,
        "resolved": True,
    }
    session.add_all(
        [
            PaperAuthorshipMetadata(
                paper_id="p1",
                author_id="a1",
                author_order=0,
                author_position="first",
                is_corresponding=False,
                affiliations=[uoft, oxford],
                sources=["openalex"],
                source_record_ids=["W1"],
                quality_flags=[],
                provenance_hash="hash-a1",
            ),
            PaperAuthorshipMetadata(
                paper_id="p1",
                author_id="a2",
                author_order=1,
                author_position="last",
                is_corresponding=True,
                affiliations=[uoft],
                sources=["openalex"],
                source_record_ids=["W1"],
                quality_flags=[],
                provenance_hash="hash-a2",
            ),
        ]
    )
    session.commit()


def test_snapshot_preserves_all_authors_and_fractional_affiliations(session, tmp_path):
    source = _write_source(tmp_path)
    _seed(session, source)

    snapshot = build_tier1_metadata_snapshot(
        session,
        source,
        created_at=datetime(2025, 1, 2, tzinfo=UTC),
    )

    artifacts = {artifact.name: artifact for artifact in snapshot.artifacts}
    assert artifacts["source/tier1.csv"].content == source.read_bytes()
    assert artifacts["authorships.jsonl"].rows == 2
    assert artifacts["affiliations.jsonl"].rows == 3
    assert artifacts["author_institution_map.csv"].rows == 3
    assert artifacts["paper_institution_map.csv"].rows == 2
    scores = list(
        csv.DictReader(
            io.StringIO(artifacts["institution_scores_default.csv"].content.decode())
        )
    )
    uoft = next(row for row in scores if row["name"] == "University of Toronto")
    oxford = next(row for row in scores if row["name"] == "University of Oxford")
    assert float(uoft["weighted_credit"]) == 0.75
    assert float(oxford["weighted_credit"]) == 0.25
    assert (
        snapshot.manifest["default_comparison"]["production_replay_check"] == "passed"
    )


def test_author_institution_export_preserves_papers_without_authorships() -> None:
    content = build_author_institution_map_csv(
        [
            {"paper_id": "p1", "doi": "10.1000/one", "title": "With authors"},
            {"paper_id": "p2", "doi": "10.1000/two", "title": "Without authors"},
        ],
        [
            {
                "paper_id": "p1",
                "doi": "10.1000/one",
                "paper_title": "With authors",
                "author_id": "a1",
                "author_name": "Author One",
                "author_rank_one_based": 1,
                "author_count": 1,
                "author_position": "first",
                "is_first": True,
                "is_last": True,
                "is_corresponding": False,
                "openalex_author_id": None,
                "orcid": None,
                "provenance_hash": "hash-a1",
            }
        ],
        [],
    )

    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8"))))
    assert {row["paper_id"] for row in rows} == {"p1", "p2"}
    missing = next(row for row in rows if row["paper_id"] == "p2")
    assert missing["mapping_status"] == "no_authorship_metadata"
    assert missing["author_name"] == ""
    assert missing["institution_name"] == ""


def test_upload_verifies_objects_and_publishes_manifest_last(session, tmp_path):
    source = _write_source(tmp_path)
    _seed(session, source)
    snapshot = build_tier1_metadata_snapshot(session, source)

    class FakeS3:
        def __init__(self):
            self.objects = {}
            self.put_order = []

        def head_object(self, *, Bucket, Key):
            if Key not in self.objects:
                raise ClientError(
                    {"Error": {"Code": "404", "Message": "Not Found"}},
                    "HeadObject",
                )
            value = self.objects[Key]
            return {
                "ContentLength": len(value["Body"]),
                "Metadata": value["Metadata"],
            }

        def put_object(self, **kwargs):
            self.objects[kwargs["Key"]] = kwargs
            self.put_order.append(kwargs["Key"])

        def get_object(self, *, Bucket, Key):
            return {"Body": io.BytesIO(self.objects[Key]["Body"])}

    client = FakeS3()
    result = upload_tier1_metadata_snapshot(
        snapshot,
        s3_client=client,
        bucket="test-bucket",
    )

    assert result["status"] == "uploaded_and_verified"
    assert result["raw_prefix"].startswith("raw/metadata/tier1/")
    assert f"snapshot_id={result['snapshot_id']}" in result["raw_prefix"]
    assert client.put_order[-1] == result["manifest_key"]
    assert result["manifest_key"].startswith("manifests/metadata/tier1/")
    assert all(row["verified"] for row in result["artifacts"])
