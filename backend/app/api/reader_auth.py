import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.reading import Reader, ReaderSession
from app.services import reader_auth as auth
from app.services.access_control import identity as reader_identity

router = APIRouter(prefix='/auth', tags=['reading identity'])


@router.post('/connect', dependencies=[Depends(auth.require_same_origin)])
def connect(response: Response):
    code, verifier, expiry = auth.begin_pairing()
    response.set_cookie(auth.PAIR_COOKIE, code + '.' + verifier, max_age=300,
                        secure=True, httponly=True, samesite='strict', path='/')
    return {'code': code, 'expires_at': expiry, 'command': '/papers login ' + code,
            'slack_url': 'https://slack.com/app_redirect?app=' + os.environ.get('PAS_SLACK_APP_ID', '')}


@router.post('/connect/complete', dependencies=[Depends(auth.require_same_origin)])
def complete(request: Request, response: Response, session: Session = Depends(get_session)):
    claim = auth.finish_pairing(request.cookies.get(auth.PAIR_COOKIE, ''))
    if not claim:
        return {'status': 'pending'}
    identity = 'slack_' + auth.digest(claim['team_id'] + ':' + claim['user_id'])[:40]
    user = session.get(Reader, identity)
    if not user:
        user = Reader(id=identity, workspace_id=claim['team_id'], slack_user_id=claim['user_id'],
                      name=claim.get('name') or claim['user_id'], active=True)
        session.add(user)
        session.flush()
    if not user.active:
        raise HTTPException(403, 'This account has been disabled.')
    token = secrets.token_urlsafe(32)
    session.add(ReaderSession(token_hash=auth.digest(token), reader_id=user.id,
                              expires=int(time.time()) + auth.SESSION_SECONDS))
    session.commit()
    response.delete_cookie(auth.PAIR_COOKIE, secure=True, httponly=True, samesite='strict', path='/')
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_SECONDS,
                        secure=True, httponly=True, samesite='lax', path='/')
    return {'status': 'signed_in', 'user': reader_identity(session, user)}


@router.get('/me')
def me(user: Reader = Depends(auth.current_reader), session: Session = Depends(get_session)):
    return reader_identity(session, user)


@router.post('/logout', dependencies=[Depends(auth.require_same_origin)])
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    token = request.cookies.get(auth.COOKIE)
    login = session.get(ReaderSession, auth.digest(token)) if token else None
    if login:
        session.delete(login)
        session.commit()
    response.delete_cookie(auth.COOKIE, secure=True, httponly=True, samesite='lax', path='/')
    return {'status': 'signed_out'}
