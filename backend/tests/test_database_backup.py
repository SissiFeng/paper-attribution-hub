from __future__ import annotations

import sqlite3

from app.scripts import backup_database_to_s3
from app.scripts.backup_database_to_s3 import _backup_sqlite, _sha256


def test_sqlite_backup_is_consistent_and_hashable(tmp_path):
    source = tmp_path / "source.sqlite3"
    target = tmp_path / "target.sqlite3"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE records (value TEXT NOT NULL)")
        database.execute("INSERT INTO records VALUES ('preserved')")
        database.commit()

    _backup_sqlite(source, target)

    with sqlite3.connect(target) as database:
        assert database.execute("SELECT value FROM records").fetchone() == (
            "preserved",
        )
    assert len(_sha256(target)) == 64


def test_backup_prints_reference_only_after_s3_verification(
    tmp_path,
    monkeypatch,
    capsys,
):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE records (value TEXT NOT NULL)")
        database.execute("INSERT INTO records VALUES ('preserved')")
        database.commit()

    class FakeS3:
        uploaded: bytes
        metadata: dict[str, str]
        manifest: bytes

        def upload_file(self, filename, _bucket, _key, ExtraArgs):
            self.uploaded = open(filename, "rb").read()
            self.metadata = ExtraArgs["Metadata"]

        def head_object(self, **_kwargs):
            return {
                "ContentLength": len(self.uploaded),
                "Metadata": self.metadata,
            }

        def put_object(self, **kwargs):
            self.manifest = kwargs["Body"]

    fake_s3 = FakeS3()
    monkeypatch.setattr(
        backup_database_to_s3.settings,
        "database_url",
        f"sqlite:///{source}",
    )
    monkeypatch.setattr(
        backup_database_to_s3.settings,
        "s3_artifacts_bucket",
        "verified-backups",
    )
    monkeypatch.setattr(
        backup_database_to_s3.boto3,
        "client",
        lambda *_args, **_kwargs: fake_s3,
    )

    assert backup_database_to_s3.main() == 0
    output = capsys.readouterr().out
    assert "s3://verified-backups/database-backups/" in output
    assert b'"sha256"' in fake_s3.manifest
