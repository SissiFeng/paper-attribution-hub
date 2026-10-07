"""Default-deny API access. Grants never override private discussion ownership."""
import time
import uuid
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db import get_session
from app.models.access import AdminGrant, AccessAudit
from app.models.reading import Reader
from app.services.reader_auth import current_reader, public_reader

PUBLIC = {('GET', '/health'), ('POST', '/auth/connect'),
          ('POST', '/auth/connect/complete'), ('POST', '/auth/logout'),
          ('GET', '/catalog/papers'), ('GET', '/catalog/papers/{paper_id}'), ('GET', '/catalog/resolve')}
PUBLIC.update({('GET', '/catalog/paper-view'), ('GET', '/catalog/papers/{paper_id}/view'),
               ('GET', '/catalog/papers/{paper_id}/wiki')})
MEMBER = {
    ('GET', '/auth/me'), ('GET', '/reading/papers'), ('GET', '/reading/papers/{paper_id}'),
    ('GET', '/reading/papers/{paper_id}/markdown'), ('GET', '/reading/resolve'),
    ('PUT', '/reading/saved/{paper_id}'), ('DELETE', '/reading/saved/{paper_id}'),
    ('POST', '/reading/compare'), ('GET', '/chat/sessions'), ('POST', '/chat/sessions'),
    ('GET', '/chat/sessions/{session_id}'), ('POST', '/chat/sessions/{session_id}/messages'),
    ('POST', '/chat/sessions/{session_id}/messages/stream'), ('GET', '/chat/members'),
    ('GET', '/chat/sessions/{session_id}/members'), ('PUT', '/chat/sessions/{session_id}/members'),
    ('POST', '/chat/sessions/{session_id}/share'), ('POST', '/chat/sessions/{session_id}/comments'),
}
MEMBER.update({
    ('GET', '/reading/papers/{paper_id}/sources/{kind}/{source_id}'),
    ('GET', '/reading/model'),
    ('GET', '/research/projects'),
    ('POST', '/research/projects'),
    ('GET', '/research/projects/{project_id}'),
    ('PUT', '/research/projects/{project_id}/members'),
    ('PUT', '/research/projects/{project_id}/papers/{paper_id}'),
    ('DELETE', '/research/projects/{project_id}/papers/{paper_id}'),
    ('POST', '/research/projects/{project_id}/discussions'),
    ('GET', '/research/annotations'),
    ('POST', '/research/annotations'),
    ('PUT', '/research/annotations/{annotation_id}'),
    ('DELETE', '/research/annotations/{annotation_id}'),
    ('POST', '/research/annotations/{annotation_id}/copy'),
    ('GET', '/research/comparisons'),
    ('POST', '/research/comparisons'),
    ('GET', '/research/comparisons/{comparison_id}'),
    ('DELETE', '/research/comparisons/{comparison_id}'),
    ('PUT', '/research/comparisons/{comparison_id}/cells'),
    ('POST', '/research/comparisons/{comparison_id}/copy'),
})
# These service routes already require the dedicated Jev key, not browser identity.
MEMBER.update({
    ('GET', '/research/projects/{project_id}/exploration'),
    ('GET', '/research/projects/{project_id}/exploration/related'),
    ('PUT', '/research/projects/{project_id}/exploration/watch'),
    ('POST', '/research/projects/{project_id}/exploration/check'),
    ('POST', '/research/projects/{project_id}/exploration/alerts/{paper_id}/seen'),
    ('PUT', '/research/projects/{project_id}/exploration/screening/{paper_id}'),
    ('POST', '/research/projects/{project_id}/exploration/connections'),
    ('DELETE', '/research/projects/{project_id}/exploration/connections/{connection_id}'),
})

SERVICE = {('GET', '/jev/status'), ('POST', '/jev/evaluate'), ('GET', '/jev/decisions'),
           ('POST', '/jev/decisions/{decision_id}/feedback')}


def is_admin(session, user):
    return bool(user.active and session.get(AdminGrant, user.id))


def identity(session, user):
    return {**public_reader(user), 'role': 'admin' if is_admin(session, user) else 'member'}


def require_admin(user: Reader = Depends(current_reader), session: Session = Depends(get_session)):
    if not is_admin(session, user):
        raise HTTPException(403, 'This page requires PAS admin access.')
    return user


def authorize_route(request: Request, session: Session = Depends(get_session)):
    route = (request.method, request.scope['route'].path)
    if route in PUBLIC or route in SERVICE:
        return
    user = current_reader(request, session)
    request.state.reader = user
    if route not in MEMBER:
        require_admin(user, session)


def lock_workspace(session, workspace):
    # Serialize grant/revoke and bootstrap even when the admin set is empty.
    if session.bind.dialect.name == 'sqlite':
        connection = session.connection()
        if not connection.connection.driver_connection.in_transaction:
            session.execute(text('BEGIN IMMEDIATE'))
    if session.bind.dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'pas-access:' + workspace})


def audit(session, actor, target, action, changes, *, audit_id=None):
    session.add(AccessAudit(id=audit_id or str(uuid.uuid4()), workspace_id=actor.workspace_id,
        actor_id=actor.id, target_id=target.id, action=action, changes=changes, created_at=int(time.time())))


def bootstrap_admin(session, workspace, slack_user):
    """Explicit deployment operation, once per workspace; never an auth fallback."""
    lock_workspace(session, workspace)
    marker = 'bootstrap:' + workspace
    if session.get(AccessAudit, marker):
        return
    user = session.scalar(select(Reader).where(Reader.workspace_id == workspace,
        Reader.slack_user_id == slack_user, Reader.active.is_(True)))
    if not user:
        raise RuntimeError('Initial admin must have completed Slack sign-in first.')
    if not session.get(AdminGrant, user.id):
        session.add(AdminGrant(reader_id=user.id))
    audit(session, user, user, 'bootstrap_admin', {'role': ['member', 'admin']}, audit_id=marker)
    session.commit()
