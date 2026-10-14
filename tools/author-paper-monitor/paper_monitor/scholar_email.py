"""Google Scholar author alerts over Microsoft Graph or read-only IMAP.

Optional verified mailbox configuration. Uses read-only IMAP and durable UIDs;
unknown author-alert layouts fail visibly without advancing the read cursor.
No Scholar website is scraped. Real-mail acceptance is required before enabling.

NOTE: the HTML layout is based on observed alert emails; validate against a
real alert from your inbox before relying on it (see README).
"""
from __future__ import annotations

import email
import html
import imaplib
import os
import re
import ssl
import urllib.parse
from email.header import decode_header, make_header

from .models import Paper

SENDER = "scholaralerts-noreply@google.com"
TITLE_RE = re.compile(
    r'<a\b(?=[^>]*\bclass=[\"\'][^\"\']*\bgse_alrt_title\b[^\"\']*[\"\'])'
    r'[^>]*\bhref=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>\s*(?:</h3>)?\s*'
    r'<div[^>]*>(.*?)</div>', re.S | re.I)
SUBJECT_RE = re.compile(r"^(?:New articles by |New citations to |)(.*?)(?: - new articles| - new related research)?$", re.I)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _real_url(href: str) -> str:
    href = html.unescape(href)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return q.get("url", [href])[0]


def parse_alert(html_body: str, subject: str) -> list[Paper]:
    m = SUBJECT_RE.match(subject.strip())
    who = m.group(1).strip() if m else subject.strip()
    out = []
    for href, title_html, meta_html in TITLE_RE.findall(html_body):
        meta = _text(meta_html)              # "A Smith, B Jones - Nature, 2026"
        authors_part, _, venue_part = meta.partition(" - ")
        url = _real_url(href)
        doi = re.search(r"10\.\d{4,9}/[^\s?#&]+", url)
        arxiv = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:\.pdf)?$", url)
        out.append(Paper(
            title=re.sub(r"^(?:\[(?:PDF|HTML|BOOK|CITATION|DOC)\]\s*)+", "", _text(title_html), flags=re.I),
            url=url,
            doi=doi.group(0) if doi else None,
            arxiv_id=arxiv.group(1) if arxiv else None,
            venue=venue_part.rsplit(",", 1)[0].strip() or None,
            authors=[a.strip() for a in authors_part.split(",") if a.strip()],
            tracked_authors=[who],
            sources=["scholar_alert"],
        ))
    return out


def _html_part(msg: email.message.Message) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    return ""


_config = None


def configure(config):
    global _config
    _config = config


def configuration():
    if _config is not None:
        return _config
    if all(os.environ.get(k) for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD")):
        return {'host': os.environ['IMAP_HOST'], 'user': os.environ['IMAP_USER'],
                'password': os.environ['IMAP_PASSWORD'], 'folder': os.environ.get('IMAP_FOLDER', 'INBOX')}
    return None


def configured() -> bool:
    return configuration() is not None


class MailboxError(ValueError):
    pass


def open_mailbox(config):
    box = imaplib.IMAP4_SSL(config['host'], port=993, timeout=20, ssl_context=ssl.create_default_context())
    try:
        box.login(config['user'], config['password'])
        status, _ = box.select(config.get('folder', 'INBOX'), readonly=True)
        if status != 'OK':
            raise MailboxError('Cannot open the configured alert folder read-only')
        return box
    except Exception:
        box.logout()
        raise


def number(box, field):
    _, values = box.response(field)
    if not values or not values[0]:
        raise MailboxError('Mailbox did not provide '+field)
    return int(values[0])


def alert_author(subject, authors, aliases=None):
    from .models import normalize_title
    if subject.strip().casefold() == 'confirm your scholar alert':
        return None  # Subscription confirmation is not a new-paper message.
    match = re.fullmatch(r'(?:New articles by (.+)|(.+) - new articles)', subject.strip(), re.I)
    if not match:
        if re.search(r'new citations|new related research|new results|Google Scholar Alert', subject, re.I):
            return None
        raise MailboxError('Unsupported Scholar subject; cursor was not advanced')
    raw_name = match.group(1) or match.group(2)
    name = normalize_title((aliases or {}).get(raw_name, raw_name))
    hits = [a.name for a in authors if normalize_title(a.name) == name]
    if len(hits) != 1:
        raise MailboxError('Scholar author alert is not uniquely mapped to the active watchlist')
    return hits[0]


def read_message(box, uid):
    status, sizes = box.uid('fetch', str(uid), '(RFC822.SIZE)')
    sizes = b' '.join(x for x in sizes if isinstance(x, bytes))
    match = re.search(rb'RFC822.SIZE (\d+)', sizes)
    if status != 'OK' or not match or int(match.group(1)) > 2_000_000:
        raise MailboxError('Scholar message is missing or exceeds the size limit')
    status, parts = box.uid('fetch', str(uid), '(BODY.PEEK[])')
    bodies = [p[1] for p in parts if isinstance(p, tuple) and isinstance(p[1], bytes)]
    if status != 'OK' or not bodies:
        raise MailboxError('Cannot read the Scholar message')
    return email.message_from_bytes(bodies[0])


def parse_message(msg, authors, aliases=None):
    from email.utils import parseaddr
    if parseaddr(msg.get('From', ''))[1].lower() != SENDER:
        return []
    subject = str(make_header(decode_header(msg.get('Subject', ''))))
    who = alert_author(subject, authors, aliases)
    if who is None:  # Citation and topic alerts are not publications by a watched author.
        return []
    papers = parse_alert(_html_part(msg), subject)
    if not papers or any(not p.title or not p.url or urllib.parse.urlsplit(p.url).scheme not in ('https', 'http') for p in papers):
        raise MailboxError('Unrecognized Scholar author-alert layout; cursor was not advanced')
    for paper in papers:
        paper.tracked_authors = [who]
    return papers


def fetch_pending(store, authors, config=None):
    import hashlib
    import json
    config = config or configuration()
    if not config:
        return [], None
    if config.get('provider') == 'graph':
        from . import scholar_graph
        return scholar_graph.fetch_pending(store, authors, config)
    identity = hashlib.sha256(json.dumps([config['host'], config['user'], config.get('folder', 'INBOX')]).encode()).hexdigest()
    key = 'scholar_cursor:'+identity
    cursor = json.loads(store.meta(key) or '{}')
    with open_mailbox(config) as box:
        validity = number(box, 'UIDVALIDITY')
        expected = cursor.get('uidvalidity', config.get('uidvalidity'))
        if expected is not None and expected != validity:
            raise MailboxError('Mailbox UIDVALIDITY changed; revalidate before resuming')
        last = cursor.get('last_uid', config.get('start_uid', 0))
        status, data = box.uid('search', None, 'UID', f'{last+1}:*', 'FROM', '"'+SENDER+'"')
        if status != 'OK':
            raise MailboxError('Scholar mailbox search failed')
        ids = sorted(int(i) for i in data[0].split() if int(i) > last)[:100]
        papers = []
        for uid in ids:
            papers.extend(parse_message(read_message(box, uid), authors, config.get('author_aliases')))
        # Caller commits this only after all returned publications are durably stored.
        return papers, (key, json.dumps({'uidvalidity': validity, 'last_uid': ids[-1] if ids else last,
                                       'messages': len(ids)}))
