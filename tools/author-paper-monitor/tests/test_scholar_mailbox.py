from pathlib import Path
import ssl
from types import SimpleNamespace

import pytest

from paper_monitor import scholar_email
from paper_monitor.authors import Author
from paper_monitor.store import Store

FX = Path(__file__).parent / "fixtures/scholar_alert.html"
AUTHORS = [Author("Anatole von Lilienfeld")]


def message(subject="Anatole von Lilienfeld - new articles", body=None, sender=None):
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = sender or scholar_email.SENDER
    msg["Subject"] = subject
    msg.set_content(body if body is not None else FX.read_text(), subtype="html")
    return msg


def test_real_sender_and_author_only_not_citations_or_unmatched_names():
    assert len(scholar_email.parse_message(message(), AUTHORS)) == 2
    assert not scholar_email.parse_message(
        message(subject="New citations to Anatole von Lilienfeld"), AUTHORS
    )
    assert not scholar_email.parse_message(
        message(sender="somebody@example.org"), AUTHORS
    )
    with pytest.raises(scholar_email.MailboxError, match="uniquely mapped"):
        scholar_email.parse_message(
            message(subject="Unknown Author - new articles"), AUTHORS
        )
    with pytest.raises(scholar_email.MailboxError, match="subject"):
        scholar_email.parse_message(
            message(subject="Changed Scholar alert format"), AUTHORS
        )


def test_unknown_html_fails_instead_of_silent_empty_result():
    with pytest.raises(scholar_email.MailboxError, match="layout"):
        scholar_email.parse_message(message(body="<html>New layout</html>"), AUTHORS)


def test_explicit_author_alias_is_applied():
    ps = scholar_email.parse_message(
        message(subject="A. von Lilienfeld - new articles"),
        AUTHORS,
        {"A. von Lilienfeld": "Anatole von Lilienfeld"},
    )
    assert ps[0].tracked_authors == ["Anatole von Lilienfeld"]


class Mailbox:
    def __init__(self, *, validity=5, malformed=False):
        self.validity = validity
        self.malformed = malformed
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def response(self, field):
        return field, [str(self.validity if field == "UIDVALIDITY" else 44).encode()]

    def uid(self, operation, *args):
        self.calls.append((operation, args))
        if operation == "search":
            return "OK", [b"40 41 42"]
        if args[1] == "(RFC822.SIZE)":
            return "OK", [b"1 (UID 42 RFC822.SIZE 5000)"]
        return "OK", [
            (
                b"42",
                message(
                    body="<html>Unknown</html>" if self.malformed else None
                ).as_bytes(),
            )
        ]


def test_imap_uid_replay_and_readonly_tls(tmp_path, monkeypatch):
    box = Mailbox()
    config = {
        "host": "imap.example.org",
        "user": "alerts@example.org",
        "password": "secret",
        "uidvalidity": 5,
        "start_uid": 40,
    }
    monkeypatch.setattr(scholar_email, "open_mailbox", lambda _: box)
    store = Store(tmp_path / "s.db")
    papers, cursor = scholar_email.fetch_pending(store, AUTHORS, config)
    assert len(papers) == 4 and store.meta(cursor[0]) is None
    assert all(
        "PEEK" in args[1] or "SIZE" in args[1]
        for op, args in box.calls
        if op == "fetch"
    )
    store.set_meta(*cursor)
    store.commit()
    papers, _ = scholar_email.fetch_pending(store, AUTHORS, config)
    assert not papers
    store.close()


def test_uid_validity_or_bad_message_does_not_advance(tmp_path, monkeypatch):
    config = {
        "host": "imap.example.org",
        "user": "alerts@example.org",
        "password": "secret",
        "uidvalidity": 5,
        "start_uid": 40,
    }
    store = Store(tmp_path / "s.db")
    for box in (Mailbox(validity=6), Mailbox(malformed=True)):
        monkeypatch.setattr(scholar_email, "open_mailbox", lambda _, box=box: box)
        with pytest.raises(scholar_email.MailboxError):
            scholar_email.fetch_pending(store, AUTHORS, config)
    assert not store.db.execute(
        "SELECT 1 FROM metadata WHERE key LIKE 'scholar_cursor:%'"
    ).fetchone()
    store.close()


def test_tls_certificate_check_and_readonly_folder(monkeypatch):
    calls = {}
    box = SimpleNamespace(
        login=lambda *_: None,
        select=lambda folder, readonly: (
            calls.update(folder=folder, readonly=readonly) or ("OK", [])
        ),
        logout=lambda: None,
    )

    def connect(host, **kwargs):
        calls.update(kwargs)
        return box

    monkeypatch.setattr(scholar_email.imaplib, "IMAP4_SSL", connect)
    scholar_email.open_mailbox(
        {
            "host": "imap.example.org",
            "user": "alerts",
            "password": "secret",
            "folder": "Scholar",
        }
    )
    assert (
        calls["ssl_context"].verify_mode == ssl.CERT_REQUIRED
        and calls["ssl_context"].check_hostname
    )
    assert calls["readonly"] is True


def test_setup_requires_real_parseable_mail_and_uses_activation_boundary(monkeypatch):
    import importlib

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "deploy"))
    setup = importlib.import_module("configure_scholar")
    monkeypatch.setattr(scholar_email, "open_mailbox", lambda _: Mailbox())
    config, report = setup.verify(
        {
            "host": "imap.example.org",
            "user": "alerts",
            "password": "secret",
            "folder": "INBOX",
        },
        AUTHORS,
    )
    assert (
        config["start_uid"] == 43
        and config["uidvalidity"] == 5
        and report["parsed_papers"] == 2
    )
    monkeypatch.setattr(
        scholar_email, "open_mailbox", lambda _: Mailbox(malformed=True)
    )
    with pytest.raises(scholar_email.MailboxError):
        setup.verify({}, AUTHORS)
