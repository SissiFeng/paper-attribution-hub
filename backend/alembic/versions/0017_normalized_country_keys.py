"""Persist Unicode-normalized country keys for dialect-stable filtering.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-01
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels = None
depends_on = None

_ALIASES = {
    "u.k.": "unitedkingdom",
    "uk": "unitedkingdom",
    "u.s.": "unitedstates",
    "u.s.a.": "unitedstates",
    "unitedstatesofamerica": "unitedstates",
    "us": "unitedstates",
    "usa": "unitedstates",
}


def _country_keys(value: str | None) -> list[str]:
    output: list[str] = []
    for part in (value or "").split(";"):
        compact = "".join(part.split()).casefold()
        decomposed = unicodedata.normalize("NFKD", compact)
        identity = "".join(
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
        )
        identity = _ALIASES.get(identity, identity)
        if not identity:
            continue
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if key not in output:
            output.append(key)
    return output


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column(
            "country_keys",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    bind = op.get_bind()
    institutions = sa.table(
        "institutions",
        sa.column("id", sa.String()),
        sa.column("country", sa.String()),
        sa.column("country_keys", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(institutions.c.id, institutions.c.country)
    ).mappings()
    for row in rows:
        bind.execute(
            institutions.update()
            .where(institutions.c.id == row["id"])
            .values(country_keys=_country_keys(row["country"]))
        )


def downgrade() -> None:
    op.drop_column("institutions", "country_keys")
