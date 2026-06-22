"""Gedeelde kolom-types.

``JSON_LIST`` = een JSON-lijst die op **Postgres** als ``JSONB`` landt en elders
(SQLite in tests) als gewone ``JSON``. JSONB is nodig omdat een gewone ``json``-
kolom in Postgres geen equality-operator heeft → ``SELECT DISTINCT`` over een rij
mét zo'n kolom faalt ("could not identify an equality operator for type json").
De ledengids distinct't hele Profile-rijen, dus elke list-kolom dáárop moet jsonb zijn.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Variant: jsonb op Postgres, json overal anders.
JSON_LIST = JSON().with_variant(JSONB, "postgresql")
