"""Lab registry generator: PI→lab entries, slugs, aliases, yaml round-trip."""
from __future__ import annotations

from app.models import SdlLab
from app.scripts.build_lab_registry import build_labs, write_registry
from app.services.lab_service import load_labs_from_yaml

CSV_HEADER = "person_id,name,aliases,institution,department,lab,role,is_ac_member,orcid\n"


def _write_csv(tmp_path, rows: list[str]):
    path = tmp_path / "members.csv"
    path.write_text(CSV_HEADER + "".join(rows), encoding="utf-8")
    return path


def test_build_labs_pi_rows_with_aliases(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            'A001,Alán Aspuru-Guzik,"A. Aspuru-Guzik; Aspuru-Guzik, A.",'
            "University of Toronto,,,PI,true,0000-0003-1024-3325\n",
            "A002,Owen Melville,O. Melville,University of Toronto,,,Staff,true,\n",
            "A003,Vijay Narasimhan,V. Narasimhan,Google DeepMind,,,Member,true,\n",
        ],
    )
    labs = build_labs(csv_path)
    # Non-PI rows (Staff / Member / Affiliate) are skipped.
    assert len(labs) == 1
    lab = labs[0]
    assert lab["id"] == "aspuru-guzik-lab"
    assert lab["name"] == "Alán Aspuru-Guzik Group"
    assert lab["institution"] == "University of Toronto"
    assert lab["pi_names"] == ["Alán Aspuru-Guzik"]
    assert lab["domain_focus"] == ""
    # Roster = PI name + parsed "; "-separated aliases.
    assert lab["member_author_names"] == [
        "Alán Aspuru-Guzik",
        "A. Aspuru-Guzik",
        "Aspuru-Guzik, A.",
    ]


def test_build_labs_slug_collision_and_determinism(tmp_path):
    csv_path = _write_csv(
        tmp_path,
        [
            "A001,Bowen Li,,University of Toronto,,,PI,true,\n",
            "A002,Kangming Li,,University of Toronto,,,PI,true,\n",
            "A003,Jason Hein,,University of British Columbia,,,PI,true,\n",
        ],
    )
    labs = build_labs(csv_path)
    # Shared surname → given-name initial appended; unique surname stays plain.
    assert [lab["id"] for lab in labs] == ["li-b-lab", "li-k-lab", "hein-lab"]
    # Deterministic across runs.
    assert build_labs(csv_path) == labs


def test_registry_round_trips_through_loader(tmp_path, session):
    csv_path = _write_csv(
        tmp_path,
        [
            'A001,Alán Aspuru-Guzik,"Alan Aspuru-Guzik; Aspuru-Guzik, A.",'
            "University of Toronto,,,PI,true,\n",
        ],
    )
    out = tmp_path / "labs.yaml"
    write_registry(build_labs(csv_path), out)

    summary = load_labs_from_yaml(session, path=out)
    assert summary == {"created": 1, "updated": 0}
    lab = session.get(SdlLab, "aspuru-guzik-lab")
    assert lab is not None
    assert lab.name == "Alán Aspuru-Guzik Group"
    assert lab.member_author_names == [
        "Alán Aspuru-Guzik",
        "Alan Aspuru-Guzik",
        "Aspuru-Guzik, A.",
    ]
    assert lab.platform_stack is None
    assert lab.automation_level is None
