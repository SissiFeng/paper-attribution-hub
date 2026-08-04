"""Versioned country-token normalization shared by writes and filters."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

_COUNTRY_IDENTITY_ALIASES = {
    "u.k.": "unitedkingdom",
    "uk": "unitedkingdom",
    "u.s.": "unitedstates",
    "u.s.a.": "unitedstates",
    "unitedstatesofamerica": "unitedstates",
    "us": "unitedstates",
    "usa": "unitedstates",
}

_COUNTRY_DISPLAY_BY_IDENTITY = {
    "australia": "Australia",
    "brazil": "Brazil",
    "canada": "Canada",
    "china": "China",
    "france": "France",
    "germany": "Germany",
    "india": "India",
    "israel": "Israel",
    "italy": "Italy",
    "japan": "Japan",
    "netherlands": "Netherlands",
    "newzealand": "New Zealand",
    "norway": "Norway",
    "reunion": "Réunion",
    "saudiarabia": "Saudi Arabia",
    "singapore": "Singapore",
    "southafrica": "South Africa",
    "southkorea": "South Korea",
    "spain": "Spain",
    "sweden": "Sweden",
    "switzerland": "Switzerland",
    "turkiye": "Türkiye",
    "unitedkingdom": "United Kingdom",
    "unitedstates": "United States",
}


@dataclass(frozen=True, slots=True)
class CanonicalCountry:
    identity: str
    key: str
    display: str


def _raw_country_identity_v1(value: str) -> str:
    compact = "".join(value.split()).casefold()
    decomposed = unicodedata.normalize("NFKD", compact)
    return "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )


def country_identity_v1(value: str) -> str:
    """Canonical Unicode identity; keep stable after migration 0017 ships."""
    raw_identity = _raw_country_identity_v1(value)
    return _COUNTRY_IDENTITY_ALIASES.get(raw_identity, raw_identity)


def country_key_v1(value: str) -> str:
    identity = country_identity_v1(value)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def country_display_v1(identity: str) -> str:
    """Return one deterministic display value for a normalized identity."""
    return _COUNTRY_DISPLAY_BY_IDENTITY.get(identity, identity.title())


def canonical_country_entries(value: str | None) -> list[CanonicalCountry]:
    output: list[CanonicalCountry] = []
    seen: set[str] = set()
    for part in (value or "").split(";"):
        compact = " ".join(part.split())
        if not compact:
            continue
        identity = country_identity_v1(compact)
        if not identity or identity in seen:
            continue
        output.append(
            CanonicalCountry(
                identity=identity,
                key=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                display=country_display_v1(identity),
            )
        )
        seen.add(identity)
    return output


def canonical_country_values(value: str | None) -> list[str]:
    return [entry.display for entry in canonical_country_entries(value)]


def country_keys_v1(value: str | None) -> list[str]:
    return [entry.key for entry in canonical_country_entries(value)]
