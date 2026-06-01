from __future__ import annotations

from app.models import Author, Institution, Paper, PaperAuthor
from app.services.network_service import build_coauthor_graph, graph_to_payload


def test_network_payload_exposes_normalized_bridge_score(session):
    inst_ac = Institution(id="inst_ac", canonical_name="AC", aliases=[], normalized_aliases=[], is_partner=True)
    inst_ext = Institution(id="inst_ext", canonical_name="External", aliases=[], normalized_aliases=[])
    ac = Author(id="a_ac", canonical_name="AC PI", normalized_name="ac pi", is_ac_member=True, institution=inst_ac)
    bridge = Author(id="a_bridge", canonical_name="Bridge Author", normalized_name="bridge author", institution=inst_ext)
    other = Author(id="a_other", canonical_name="Other Author", normalized_name="other author", institution=inst_ext)
    p1 = Paper(id="p_bridge_1", title="SDL one", sdl_tags=["sdl-1"])
    p2 = Paper(id="p_bridge_2", title="SDL two", sdl_tags=["sdl-2"])
    p1.authors = [
        PaperAuthor(author=ac, author_order=1),
        PaperAuthor(author=bridge, author_order=2),
    ]
    p2.authors = [
        PaperAuthor(author=bridge, author_order=1),
        PaperAuthor(author=other, author_order=2),
    ]
    session.add_all([inst_ac, inst_ext, ac, bridge, other, p1, p2])
    session.commit()

    payload = graph_to_payload(build_coauthor_graph(session))

    bridge_node = next(n for n in payload["nodes"] if n["id"] == "a_bridge")
    assert bridge_node["cross_sdl_diversity"] > 0
    assert bridge_node["bridge_score"] > 0
