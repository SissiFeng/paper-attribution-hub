from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import NetworkOut
from app.services.network_service import build_coauthor_graph, graph_to_payload

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/coauthors", response_model=NetworkOut)
def coauthor_network(
    only_relevant: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> NetworkOut:
    g = build_coauthor_graph(session, only_relevant=only_relevant)
    payload = graph_to_payload(g)
    return NetworkOut(**payload)
