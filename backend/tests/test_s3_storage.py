from io import BytesIO

from app.services import s3_storage


def test_required_s3_does_not_report_local_fallback_as_uploaded(monkeypatch):
    monkeypatch.setattr(s3_storage, "_get_s3_client", lambda: None)

    key = s3_storage.put_file(
        "zotero-fulltexts/paper",
        "attachment.pdf",
        b"%PDF-test",
        "application/pdf",
        require_s3=True,
    )

    assert key is None


def test_get_file_reads_exact_s3_key(monkeypatch):
    class FakeS3:
        def get_object(self, *, Bucket, Key):
            assert Bucket == "artifacts"
            assert Key == "raw/zotero/document.md"
            return {"Body": BytesIO(b"# Markdown")}

    monkeypatch.setattr(s3_storage.settings, "s3_artifacts_bucket", "artifacts")

    content = s3_storage.get_file(
        "raw/zotero/document.md",
        s3_client=FakeS3(),
        require_s3=True,
    )

    assert content == b"# Markdown"
