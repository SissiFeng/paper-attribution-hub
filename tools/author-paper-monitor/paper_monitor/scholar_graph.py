"""Read one shared-mailbox folder with app-only Graph and durable delta cursors.

Exchange Application RBAC must restrict this identity to the shared mailbox.
The application further restricts reads to the configured folder; it never
marks mail read or moves/deletes messages. No browser/user credentials are used.
"""
from __future__ import annotations

import email
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .scholar_email import MailboxError, SENDER, alert_author, parse_message

GRAPH = 'https://graph.microsoft.com/v1.0'


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
        if exc.code == 410:
            raise MailboxError('Microsoft delta cursor expired; revalidate and rescan the folder') from None
        raise MailboxError(f'Microsoft mailbox HTTP {exc.code}; check app authorization or retry next poll') from None
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
    validate_config(config)
    token = token or access_token(config)
    identity = [config['tenant_id'].lower(), config['mailbox'].lower(), config['folder_id']]
    key = 'scholar_graph_cursor:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    cursor = json.loads(store.meta(key) or '{}')
    link = cursor.get('delta_link') or delta_url(config) + '?' + urllib.parse.urlencode({
        '$select': 'id,from,subject,receivedDateTime,parentFolderId', '$top': '100'})
    visited, seen, papers = set(), set(), []
    messages = ignored = publication_messages = 0
    for _ in range(50):
        checked_delta_link(link, config)
        if link in visited:
            raise MailboxError('Microsoft repeated a delta page; cursor was not advanced')
        visited.add(link)
        page = request(link, token=token)
        if not isinstance(page.get('value'), list):
            raise MailboxError('Invalid Microsoft delta response')
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
            who = alert_author(item.get('subject', ''), authors, config.get('author_aliases'))
            if who is None:
                ignored += 1
                continue
            raw = request(folder_url(config) + '/messages/' + urllib.parse.quote(item['id'], safe='') + '/$value',
                          token=token, mime=True)
            parsed = parse_message(email.message_from_bytes(raw), authors, config.get('author_aliases'))
            if not parsed or any(p.tracked_authors != [who] for p in parsed):
                raise MailboxError('Microsoft metadata and Scholar message disagree')
            papers.extend(parsed)
            publication_messages += 1
        next_link, done = page.get('@odata.nextLink'), page.get('@odata.deltaLink')
        if bool(next_link) == bool(done):
            raise MailboxError('Microsoft did not return one unambiguous continuation cursor')
        if done:
            # Caller commits this alongside the papers, never before storage.
            return papers, (key, json.dumps({'delta_link': checked_delta_link(done, config),
                'messages': messages, 'ignored': ignored, 'publication_messages': publication_messages}))
        link = next_link
    raise MailboxError('Microsoft folder exceeds the bounded scan; cursor was not advanced')
