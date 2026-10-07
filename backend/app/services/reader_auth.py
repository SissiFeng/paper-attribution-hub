"""Slack proves identity; a browser-bound pairing never exposes a bot credential."""
import hashlib
import json
import os
import secrets
import time
from functools import lru_cache

import boto3
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.reading import Reader, ReaderSession

COOKIE = '__Host-pas-reader'
PAIR_COOKIE = '__Host-pas-pair'
SESSION_SECONDS = 7 * 86400


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def origin():
    return os.environ.get('PAS_PUBLIC_URL', '').rstrip('/')


def require_same_origin(request: Request):
    # A custom header blocks form CSRF; exact Origin prevents ambient-cookie
    # requests from other allowed CORS origins. Never trust a client identity ID.
    if (request.headers.get('x-pas-request') != '1' or not origin()
            or request.headers.get('origin') != origin()):
        raise HTTPException(403, 'Open PAS in its own browser tab to continue.')


@lru_cache(maxsize=1)
def pairing_table():
    name = os.environ.get('PAS_SLACK_TABLE')
    if not name or not os.environ.get('PAS_SLACK_TEAM_ID') or not origin():
        raise HTTPException(503, 'Slack sign-in is not configured.')
    return boto3.resource('dynamodb').Table(name)


def begin_pairing():
    code = '-'.join(secrets.token_hex(2).upper() for _ in range(3))
    verifier = secrets.token_urlsafe(32)
    key = 'pas-login:' + digest(code)
    expiry = int(time.time()) + 300
    pairing_table().put_item(Item={'pk': key, 'version': time.time_ns(), 'expires': expiry,
        'payload': json.dumps({'browser_hash': digest(verifier), 'expires': expiry, 'status': 'pending'})},
        ConditionExpression='attribute_not_exists(pk)')
    return code, verifier, expiry


def finish_pairing(cookie):
    from botocore.exceptions import ClientError
    try:
        code, verifier = cookie.split('.', 1)
    except ValueError:
        raise HTTPException(401, 'Start Slack sign-in again.') from None
    key = 'pas-login:' + digest(code)
    item = pairing_table().get_item(Key={'pk': key}, ConsistentRead=True).get('Item', {})
    value = json.loads(item.get('payload', '{}'))
    if (value.get('expires', 0) <= time.time()
            or not secrets.compare_digest(value.get('browser_hash', ''), digest(verifier))):
        raise HTTPException(401, 'Slack sign-in expired. Start again.')
    if value.get('status') == 'pending':
        return None
    if value.get('status') != 'verified' or value.get('team_id') != os.environ['PAS_SLACK_TEAM_ID']:
        raise HTTPException(401, 'Slack sign-in is unavailable or already used.')
    try:
        pairing_table().update_item(Key={'pk': key},
            UpdateExpression='SET payload=:p, #v=:new', ConditionExpression='#v=:old',
            ExpressionAttributeNames={'#v': 'version'}, ExpressionAttributeValues={
                ':p': json.dumps({**value, 'status': 'consumed'}), ':new': time.time_ns(), ':old': item['version']})
    except ClientError as exc:
        if exc.response['Error']['Code'] == 'ConditionalCheckFailedException':
            raise HTTPException(409, 'This sign-in has already completed.') from None
        raise
    return value


def current_reader(request: Request, session: Session = Depends(get_session)) -> Reader:
    token = request.cookies.get(COOKIE, '')
    login = session.get(ReaderSession, digest(token)) if token else None
    user = session.get(Reader, login.reader_id) if login and login.expires > time.time() else None
    if not user or not user.active or user.workspace_id != os.environ.get('PAS_SLACK_TEAM_ID'):
        raise HTTPException(401, 'Sign in with Slack to access your reading space.')
    if request.method not in ('GET', 'HEAD'):
        require_same_origin(request)
    return user


def public_reader(user):
    return {'id': user.id, 'name': user.name, 'workspace_id': user.workspace_id}
