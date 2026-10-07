"""Server-side authorization for every persisted conversation operation."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models import ChatSession
from app.models.reading import ChatParticipant, Reader


def require_chat(db, chat_id, user, *, owner_only=False, lock=False):
    statement = select(ChatSession).where(ChatSession.id == chat_id)
    if lock:
        statement = statement.with_for_update()
    chat = db.scalar(statement)
    from app.models.research import ProjectDiscussion
    from app.services.research_access import require_project
    project_link = db.get(ProjectDiscussion, chat_id) if chat else None
    if project_link:
        require_project(db, project_link.project_id, user)
        if owner_only and chat.owner_id != user.id:
            raise HTTPException(403, 'Only the discussion creator can change it.')
        return chat
    member = db.get(ChatParticipant, (chat_id, user.id)) if chat and chat.shared else None
    if (not chat or not chat.owner_id or chat.workspace_id != user.workspace_id
            or (chat.owner_id != user.id and not member)):
        raise HTTPException(404, 'Discussion not found or not shared with you.')
    from app.services.access_control import is_admin
    if chat.scope.get('access_policy') != 'paper-reading-v1' and not is_admin(db, user):
        raise HTTPException(403, 'This archived discussion predates reading permissions. Start a new discussion.')
    if owner_only and chat.owner_id != user.id:
        raise HTTPException(403, 'Only the discussion owner can change sharing.')
    return chat


def checked_members(db, ids, user):
    ids = list(dict.fromkeys(i for i in ids if i != user.id))
    if len(ids) > 20:
        raise HTTPException(422, 'Choose at most 20 discussion members.')
    members = list(db.scalars(select(Reader).where(Reader.id.in_(ids),
        Reader.workspace_id == user.workspace_id, Reader.active.is_(True))))
    if len(members) != len(ids):
        raise HTTPException(422, 'Choose registered members of your workspace.')
    return members
