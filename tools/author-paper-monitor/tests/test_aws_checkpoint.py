import contextlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError

from paper_monitor import aws_runner, cli, crossref, pas, slack, slack_app
from paper_monitor.models import Paper


class FakeS3:
    def __init__(self):
        self.objects = {"author-monitor/test/authors.csv": b"name,openalex_ids\nA,A123\n"}
        self.fail_posted_checkpoint = False

    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        return {"Contents": [{"Key": k} for k in self.objects if k.startswith(Prefix)][:MaxKeys]}

    def download_file(self, bucket, key, path):
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        Path(path).write_bytes(self.objects[key])

    def upload_file(self, path, bucket, key):
        if self.fail_posted_checkpoint and key.endswith("state.db"):
            with contextlib.closing(sqlite3.connect(path)) as db:
                if db.execute("SELECT 1 FROM papers WHERE status='posted'").fetchone():
                    raise OSError("S3 unavailable AFTER Slack accepted")
        self.objects[key] = Path(path).read_bytes()


@pytest.mark.parametrize('immediate', [False, True])
def test_lost_cloud_checkpoint_never_blindly_replays_slack(monkeypatch, tmp_path, immediate):
    import app.db

    s3 = FakeS3()
    lock = MagicMock()
    lock.closed = lock.invalidated = False
    lock.scalar.return_value = True
    engine = MagicMock()
    engine.connect.return_value.execution_options.return_value.__enter__.return_value = lock
    monkeypatch.setattr(app.db, "engine", engine)
    monkeypatch.setattr(boto3, "client", lambda _: s3)
    monkeypatch.setattr(aws_runner.signal, "alarm", lambda _: None)
    monkeypatch.setenv("MONITOR_BUCKET", "test")
    monkeypatch.setenv("MONITOR_PREFIX", "author-monitor/test")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "collect", lambda *_: ([], []))
    assert aws_runner.main([]) == 0
    paper = Paper("New paper", doi="10.1/x", authors=["A"])
    monkeypatch.setattr(cli, "collect", lambda *_: ([paper], []))
    monkeypatch.setattr(crossref, "enrich", lambda _: None)
    monkeypatch.setattr(pas, "ingest", lambda _, **kw: "pas_123")
    posts = []
    monkeypatch.setattr(slack, "post", posts.append)
    if immediate:
        monkeypatch.setenv('SLACK_BOT_TOKEN', 'test-token')
        monkeypatch.setenv('SLACK_CHANNEL_ID', 'D1')
        monkeypatch.setenv('SLACK_DELIVERY_MODE', 'immediate_weekly')
        monkeypatch.setattr(slack_app, 'api', lambda *a: posts.append(a[2]) or {'ts': '1720000000.000001'})
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    s3.fail_posted_checkpoint = True
    with pytest.raises(OSError, match="AFTER Slack"):
        aws_runner.main([])
    assert len(posts) == 1
    # A brand-new worker downloads 'sending' from S3 and does not POST again.
    s3.fail_posted_checkpoint = False
    assert aws_runner.main([]) == 1
    assert len(posts) == 1
    path = tmp_path / "downloaded.db"
    path.write_bytes(s3.objects["author-monitor/test/state.db"])
    with contextlib.closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT status FROM papers").fetchone()[0] == "sending"


def test_cloud_dry_run_cannot_mutate_production_state(monkeypatch):
    monkeypatch.setenv("MONITOR_BUCKET", "test")
    monkeypatch.delenv("MONITOR_PREFIX", raising=False)
    with pytest.raises(ValueError, match="separate MONITOR_PREFIX"):
        aws_runner.main(["--dry-run"])
