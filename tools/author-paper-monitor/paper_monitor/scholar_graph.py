"""Read one shared-mailbox folder with app-only Graph and durable delta cursors.

Exchange Application RBAC must restrict this identity to the shared mailbox.
The application further restricts reads to the configured folder; it never
marks mail read or moves/deletes messages. No browser/user credentials are used.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .scholar_email import MailboxError, SENDER

GRAPH = 'https://graph.microsoft.com/v1.0'


class GraphError(MailboxError):
    def __init__(self, code, retry_after=900):
        self.code, self.retry_after = code, retry_after
        message = ('Microsoft delta cursor expired; folder will be rescanned with durable message deduplication'
                   if code == 410 else f'Microsoft mailbox HTTP {code}; check app authorization or retry next poll')
        super().__init__(message)


def validate_config(config, *, verified=True):
    if not isinstance(config, dict) or config.get('provider') != 'graph':
        raise MailboxError('Expected a Microsoft Graph mailbox configuration')
    for key in ('tenant_id', 'client_id'):
        if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', str(config.get(key, ''))):
            raise MailboxError('Invalid Microsoft application identity')
    if not re.fullmatch(r'[^\s/@?#]+@[^\s/@?#]+\.[^\s/@?#]+', str(config.get('mailbox', ''))):
        raise MailboxError('Invalid shared mailbox address')
    for key in ('client_secret', 'folder_id', 'folder'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise MailboxError('Incomplete Microsoft mailbox configuration')
    if verified and not config.get('verified_at'):
        raise MailboxError('Verify mailbox access before enabling collection')
    from .mailbox_state import received_at
    for key in ('notify_after', 'secret_expires_at'):
        if config.get(key):
            received_at(config[key])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, *, token=None, data=None, mime=False):
    headers = {'Accept': 'message/rfc822' if mime else 'application/json'}
    if token:
        headers.update(Authorization='Bearer ' + token, Prefer='IdType="ImmutableId"')
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=25) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise MailboxError('Microsoft response exceeds the size limit')
        result = raw if mime else json.loads(raw)
        if not mime and not isinstance(result, dict):
            raise ValueError()
        return result
    except urllib.error.HTTPError as exc:
        try:
            delay = max(1, int((exc.headers or {}).get('Retry-After', '900')))
        except (TypeError, ValueError):
            delay = 900
        raise GraphError(exc.code, delay) from None
    except (OSError, ValueError) as exc:
        if isinstance(exc, MailboxError):
            raise
        # Never print OAuth bodies, client secrets, bearer tokens or cursor URLs.
        raise MailboxError('Microsoft mailbox request failed; retry next poll') from None


def access_token(config):
    result = request(f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/token",
                     data=urllib.parse.urlencode({'client_id': config['client_id'],
                         'client_secret': config['client_secret'],
                         'scope': 'https://graph.microsoft.com/.default',
                         'grant_type': 'client_credentials'}).encode())
    token = result.get('access_token')
    if not isinstance(token, str) or not token or result.get('token_type', '').lower() != 'bearer':
        raise MailboxError('Microsoft did not return a valid application access token')
    return token


def mailbox_url(config):
    return GRAPH + '/users/' + urllib.parse.quote(config['mailbox'], safe='')


def folder_url(config):
    return mailbox_url(config) + '/mailFolders/' + urllib.parse.quote(config['folder_id'], safe='')


def delta_url(config):
    return folder_url(config) + '/messages/delta'


def checked_delta_link(link, config):
    if not isinstance(link, str):
        raise MailboxError('Missing Microsoft delta cursor')
    got, expected = urllib.parse.urlsplit(link), urllib.parse.urlsplit(delta_url(config))
    if (got.scheme != 'https' or got.netloc != expected.netloc or got.fragment
            or urllib.parse.unquote(got.path) != urllib.parse.unquote(expected.path)):
        raise MailboxError('Microsoft delta link escaped the configured mailbox folder')
    return link


def fetch_pending(store, authors, config, *, token=None):
    from . import mailbox_state
    validate_config(config)
    identity = [config['tenant_id'].lower(), config['mailbox'].lower(), config['folder_id']]
    key = 'scholar_graph_cursor:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    cursor = json.loads(store.meta(key) or '{}')
    initial = delta_url(config) + '?' + urllib.parse.urlencode({
        '$select': 'id,from,subject,receivedDateTime,parentFolderId', '$top': '100'})
    link = cursor.get('next_link') or cursor.get('delta_link') or initial
    visited, seen = set(), set()
    messages = ignored = 0
    poll_ok, poll_error = False, None
    retry_key = key + ':retry_after'
    deadline = time.monotonic() + 450  # Leave time for catalogue and delivery work.

    def capture(item):
        nonlocal ignored
        message_key = mailbox_state.identity(key, item['id'])
        previous = store.db.execute('SELECT status,retry_at FROM mail_messages WHERE id=?', (message_key,)).fetchone()
        if previous and (previous[0] != 'fetch_retry' or previous[1] > time.time()):
            return
        if item.get('subject', '').strip().casefold() == 'confirm your scholar alert':
            # Confirmation contains an action link, not a publication. Keep metadata only.
            mailbox_state.capture(store, key, item)
            store.db.execute("UPDATE mail_messages SET status='ignored' WHERE id=?", (message_key,))
            ignored += 1
            return
        try:
            raw = request(folder_url(config) + '/messages/' + urllib.parse.quote(item['id'], safe='') + '/$value',
                          token=token, mime=True)
        except MailboxError as exc:
            mailbox_state.capture(store, key, item, error=str(exc), retry_after=getattr(exc, 'retry_after', 900))
            if isinstance(exc, GraphError) and exc.code in (429, 503):
                store.set_meta(retry_key, str(time.time() + exc.retry_after))
                store.commit()
                raise
        else:
            mailbox_state.capture(store, key, item, raw=raw)

    try:
        if time.time() < float(store.meta(retry_key) or 0):
            raise MailboxError('Microsoft retry interval has not elapsed')
        token = token or access_token(config)
        retries = store.db.execute("SELECT metadata FROM mail_messages WHERE mailbox_key=? AND status='fetch_retry' AND retry_at<=? ORDER BY retry_at LIMIT 20", (key, time.time())).fetchall()
        for (metadata,) in retries:
            capture(json.loads(metadata))
            if time.monotonic() >= deadline:
                raise MailboxError('Mailbox capture budget reached; durable mail will resume next poll')
        store.commit()
        for _ in range(20):
            checked_delta_link(link, config)
            if link in visited:
                raise MailboxError('Microsoft repeated a delta page')
            visited.add(link)
            page = request(link, token=token)
            if not isinstance(page.get('value'), list):
                raise MailboxError('Invalid Microsoft delta response')
            next_link, done = page.get('@odata.nextLink'), page.get('@odata.deltaLink')
            if bool(next_link) == bool(done):
                raise MailboxError('Microsoft did not return one unambiguous continuation cursor')
            checked_delta_link(next_link or done, config)
            for item in page['value']:
                if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
                    raise MailboxError('Invalid Microsoft message metadata')
                if '@removed' in item or item['id'] in seen:
                    continue
                seen.add(item['id'])
                messages += 1
                sender = ((item.get('from') or {}).get('emailAddress') or {}).get('address', '').lower()
                if sender != SENDER:
                    ignored += 1
                    continue
                capture(item)
                if time.monotonic() >= deadline:
                    raise MailboxError('Mailbox capture budget reached; durable mail will resume next poll')
            cursor = {'delta_link': done} if done else {'next_link': next_link}
            store.set_meta(key, json.dumps(cursor))
            store.commit()  # Only durable raw mail/retry records permit advancing the page.
            if done:
                poll_ok = True
                break
            link = next_link
        else:
            poll_error = 'Microsoft snapshot is continuing on the next poll'
    except MailboxError as exc:
        poll_error = str(exc)
        if isinstance(exc, GraphError):
            if exc.code == 410:
                cursor = {}  # Immutable message ledger makes a full rescan safe.
                store.set_meta(key, '{}')
            if exc.code in (429, 503):
                store.set_meta(retry_key, str(time.time() + exc.retry_after))
        store.commit()
    papers, ready = mailbox_state.parse_pending(store, key, authors, config)
    report = {**cursor, 'messages': messages, 'ignored': ignored,
              'publication_messages': len(ready), 'ready_message_ids': ready,
              'poll_ok': poll_ok, 'poll_error': poll_error}
    return papers, (key, json.dumps(report))
