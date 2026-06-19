"""Tests voor de gecureerde kennisbank + retrieval (Concierge-intelligentie F1)."""

from __future__ import annotations

import pytest

from app.services import knowledge


def test_empty_query_returns_overview():
    assert knowledge.search("") == [knowledge.overview()]
    # Alleen stopwoorden → ook overzicht (niets onderscheidends).
    assert knowledge.search("hoe is dit") == [knowledge.overview()]


@pytest.mark.parametrize(
    "query,expected_id",
    [
        ("kost dit geld?", "kosten"),
        ("hoe log ik in zonder wachtwoord?", "login"),
        ("wat gebeurt er met mijn data?", "avg"),
        ("hoe verbind ik claude code via mcp?", "verbind"),
        ("hoe stel ik me voor aan iemand?", "intro"),
        ("welke meetups zijn er?", "agenda"),
        ("kan ik mijn profiel openbaar maken?", "zichtbaarheid"),
    ],
)
def test_relevant_entry_is_retrieved(query, expected_id):
    """De grounding-garantie: het juiste fragment zit in de top-K (de agent
    krijgt het mee). Strikte top-1 is voor ambigue vragen te streng — 'profiel
    openbaar maken' raakt terecht zowel 'profiel' als 'zichtbaarheid'."""
    results = knowledge.search(query)
    assert results, f"geen resultaat voor {query!r}"
    assert expected_id in [e.id for e in results]


def test_search_respects_limit():
    results = knowledge.search("profiel matches verbind agenda nieuws", limit=2)
    assert len(results) <= 2


def test_unknown_query_returns_empty():
    assert knowledge.search("xyzzy quux frobnicate") == []


def test_results_are_deterministic():
    a = knowledge.search("hoe werkt matchmaking")
    b = knowledge.search("hoe werkt matchmaking")
    assert [e.id for e in a] == [e.id for e in b]


def test_all_entries_have_unique_ids():
    ids = [e.id for e in knowledge.KNOWLEDGE]
    assert len(ids) == len(set(ids))
