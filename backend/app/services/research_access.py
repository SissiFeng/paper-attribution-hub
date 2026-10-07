from fastapi import HTTPException
from sqlalchemy import select
from app.models.research import ResearchProject, ProjectMember


def require_project(db, project_id, user, *, owner=False, lock=False):
    stmt = select(ResearchProject).where(ResearchProject.id == project_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    project = db.scalar(stmt)
    if (not project or project.workspace_id != user.workspace_id or not user.active or
            (project.owner_id != user.id and not db.get(ProjectMember, (project.id, user.id)))):
        raise HTTPException(404, 'Project not found or not shared with you.')
    if owner and project.owner_id != user.id:
        raise HTTPException(403, 'Only the project owner can change membership.')
    return project


def require_artifact(db, model, artifact_id, user, *, edit=False):
    row = db.get(model, artifact_id)
    if not row:
        raise HTTPException(404, 'Research item not found.')
    if row.project_id:
        require_project(db, row.project_id, user, lock=edit)
    elif row.owner_id != user.id:
        raise HTTPException(404, 'Research item not found.')
    if edit and row.owner_id != user.id:
        raise HTTPException(403, 'Only the creator can edit this research item.')
    return row
