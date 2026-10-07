import os
from pathlib import PurePosixPath
import boto3
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.db import get_session
from app.models.access import AdminGrant, AccessAudit
from app.models.reading import Reader, ReaderSession
from app.services.access_control import require_admin, identity, lock_workspace, audit

router = APIRouter(prefix='/access', tags=['access'], dependencies=[Depends(require_admin)])


@router.get('/check-admin')
def check_admin():
    return {'authorized': True}


@router.get('/members')
def members(q: str = '', session: Session = Depends(get_session), actor: Reader = Depends(require_admin)):
    if len(q) > 100:
        raise HTTPException(422, 'Search is too long.')
    rows = session.scalars(select(Reader).where(Reader.workspace_id == actor.workspace_id,
        Reader.name.icontains(q, autoescape=True)).order_by(Reader.name, Reader.id).limit(200))
    return [{**identity(session, row), 'active': row.active} for row in rows]


class MemberUpdate(BaseModel):
    admin: bool
    active: bool


@router.put('/members/{reader_id}')
def update_member(reader_id: str, payload: MemberUpdate, session: Session = Depends(get_session), actor: Reader = Depends(require_admin)):
    lock_workspace(session, actor.workspace_id)
    session.expire_all()
    require_admin(actor, session)  # A concurrent revoke must take effect after the lock.
    target = session.get(Reader, reader_id)
    if not target or target.workspace_id != actor.workspace_id:
        raise HTTPException(404, 'Member not found.')
    grant = session.get(AdminGrant, target.id)
    before = {'admin': bool(grant), 'active': target.active}
    if grant and target.active and not (payload.admin and payload.active):
        other = session.scalar(select(Reader.id).join(AdminGrant, AdminGrant.reader_id == Reader.id).where(
            Reader.workspace_id == actor.workspace_id, Reader.active.is_(True), Reader.id != target.id).limit(1))
        if not other:
            raise HTTPException(409, 'Keep at least one active PAS administrator.')
    if payload.admin and not grant:
        session.add(AdminGrant(reader_id=target.id))
    elif not payload.admin and grant:
        session.delete(grant)
    target.active = payload.active
    if not payload.active:
        session.execute(delete(ReaderSession).where(ReaderSession.reader_id == target.id))
    audit(session, actor, target, 'update_member', {'before': before, 'after': payload.model_dump()})
    session.commit()
    return {**identity(session, target), 'active': target.active}


@router.get('/audit')
def audit_log(session: Session = Depends(get_session), actor: Reader = Depends(require_admin)):
    return [{'id': row.id, 'actor_id': row.actor_id, 'target_id': row.target_id,
             'action': row.action, 'changes': row.changes, 'created_at': row.created_at}
            for row in session.scalars(select(AccessAudit).where(AccessAudit.workspace_id == actor.workspace_id)
                .order_by(AccessAudit.created_at.desc(), AccessAudit.id).limit(100))]


@router.get('/files/{path:path}')
def legacy_file(path: str):
    # Only a separately snapshotted frontend prefix is readable, never arbitrary S3 data.
    if not path or '..' in path.split('/') or '\\' in path or str(PurePosixPath(path)) != path or path.startswith('/'):
        raise HTTPException(404, 'File not found.')
    bucket = os.environ.get('PAS_ADMIN_ASSETS_BUCKET')
    if not bucket:
        raise HTTPException(503, 'Administrative assets are not configured.')
    from botocore.exceptions import ClientError
    try:
        obj = boto3.client('s3').get_object(Bucket=bucket, Key='protected-legacy/' + path)
    except ClientError as exc:
        if exc.response['Error']['Code'] in ('NoSuchKey', 'AccessDenied'):
            raise HTTPException(404, 'File not found.') from None
        raise
    if obj['ContentLength'] > 25 * 1024 * 1024:
        obj['Body'].close()
        raise HTTPException(413, 'File is too large.')
    try:
        data = obj['Body'].read()
    finally:
        obj['Body'].close()
    return Response(data, media_type=obj.get('ContentType', 'application/octet-stream'),
        headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "frame-ancestors 'none'"})
