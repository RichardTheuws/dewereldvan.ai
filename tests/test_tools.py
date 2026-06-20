"""AI-toolsets op profielen (v1) — model, tool_service, ledengids-filter, AVG.

Spiegelt de tag-tests (``test_members_page.py`` / ``test_profile_completeness.py``):
service-laag op de rollback-geïsoleerde ``db``-fixture, ``Tool`` direct
geconstrueerd waar dat de tag-tests ook doen, en de fabrieken
``make_member``/``make_profile`` voor de subjecten.

De logo-verrijking is hier irrelevant: ``tool_service`` haalt GEEN logo's op (dat
doet de nachtelijke job ``app.jobs.enrich_tool_logos`` los), dus de tests blijven
hermetisch zonder netwerk of threads.
"""

from __future__ import annotations

from app.models import Tool, Visibility, profile_tool
from app.services import members_service, tool_service
from sqlalchemy import select


# --------------------------------------------------------------------------- #
# Model + assoc                                                               #
# --------------------------------------------------------------------------- #
def test_profile_tools_relationship_and_assoc(db, make_member, make_profile):
    m = make_member(email="t1@example.com", name="Tooler")
    p = make_profile(m, visibility=Visibility.public)
    claude = Tool(name="Claude Code", slug="claude-code")
    db.add(claude)
    db.flush()
    p.tools = [claude]
    db.flush()

    rows = db.execute(
        select(profile_tool.c.profile_id, profile_tool.c.tool_id)
    ).all()
    assert (p.id, claude.id) in rows
    assert [t.name for t in p.tools] == ["Claude Code"]


# --------------------------------------------------------------------------- #
# tool_service — get_or_create (dedup op slug), set_tools, add/remove          #
# --------------------------------------------------------------------------- #
def test_get_or_create_dedups_on_slug(db):
    a = tool_service.get_or_create(db, "Claude Code")
    b = tool_service.get_or_create(db, "claude code")  # andere casing
    c = tool_service.get_or_create(db, "CLAUDE CODE")
    assert a.id == b.id == c.id
    assert a.slug == "claude-code"
    # Eerste casing wint (geen overschrijven van name).
    assert a.name == "Claude Code"
    assert db.scalar(select(Tool).where(Tool.slug == "claude-code")) is not None


def test_get_or_create_fills_missing_url(db):
    a = tool_service.get_or_create(db, "Cursor")
    assert a.url is None
    b = tool_service.get_or_create(db, "Cursor", url="https://cursor.com")
    assert a.id == b.id
    assert b.url == "https://cursor.com"


def test_set_tools_replace_and_dedup(db, make_member, make_profile):
    m = make_member(email="s1@example.com", name="Setter")
    p = make_profile(m, visibility=Visibility.public)

    tool_service.set_tools(db, p, "Claude Code, Cursor, claude code")
    assert {t.slug for t in p.tools} == {"claude-code", "cursor"}

    # Replace-semantiek: een tweede set vervangt de hele set.
    tool_service.set_tools(db, p, "n8n")
    assert {t.slug for t in p.tools} == {"n8n"}

    # Lege/whitespace input → lege set.
    tool_service.set_tools(db, p, "  ,  ")
    assert p.tools == []


def test_set_tools_accepts_list(db, make_member, make_profile):
    m = make_member(email="s2@example.com", name="Lister")
    p = make_profile(m, visibility=Visibility.public)
    tool_service.set_tools(db, p, ["Claude Code", "Cursor"])
    assert {t.slug for t in p.tools} == {"claude-code", "cursor"}


def test_add_and_remove_tool(db, make_member, make_profile):
    m = make_member(email="ar@example.com", name="AddRemove")
    p = make_profile(m, visibility=Visibility.public)

    t = tool_service.add_tool(db, p, "Windsurf")
    assert t is not None
    assert {x.slug for x in p.tools} == {"windsurf"}

    # Idempotent: nogmaals toevoegen dupliceert niet.
    tool_service.add_tool(db, p, "windsurf")
    assert len(p.tools) == 1

    # Vrij toevoegen van een tool buiten de catalogus werkt.
    tool_service.add_tool(db, p, "Mijn Eigen Tool")
    assert "mijn-eigen-tool" in {x.slug for x in p.tools}

    assert tool_service.remove_tool(db, p, t.id) is True
    assert "windsurf" not in {x.slug for x in p.tools}
    # Onbekend id → False (geen crash).
    assert tool_service.remove_tool(db, p, 999999) is False


def test_add_tool_empty_name_returns_none(db, make_member, make_profile):
    m = make_member(email="empty@example.com", name="Empty")
    p = make_profile(m, visibility=Visibility.public)
    assert tool_service.add_tool(db, p, "   ") is None
    assert p.tools == []


# --------------------------------------------------------------------------- #
# Ledengids-filter — members_service.list_public_profiles(tool=...)            #
# --------------------------------------------------------------------------- #
def test_members_filter_by_tool(db, make_member, make_profile):
    a = make_member(email="ma@example.com", name="Alfa")
    pa = make_profile(a, visibility=Visibility.public)
    b = make_member(email="mb@example.com", name="Beta")
    pb = make_profile(b, visibility=Visibility.public)

    tool_service.set_tools(db, pa, "Claude Code")
    tool_service.set_tools(db, pb, "Cursor")
    db.flush()

    # Match op naam-substring (case-insensitief) én op slug.
    rows_name = members_service.list_public_profiles(db, tool="claude")
    assert {p.display_name for p in rows_name} == {"Alfa"}
    rows_slug = members_service.list_public_profiles(db, tool="cursor")
    assert {p.display_name for p in rows_slug} == {"Beta"}


def test_members_tool_filter_combines_with_tag(db, make_member, make_profile):
    from app.models import Tag

    a = make_member(email="ca@example.com", name="Alfa")
    pa = make_profile(a, visibility=Visibility.public)
    b = make_member(email="cb@example.com", name="Beta")
    pb = make_profile(b, visibility=Visibility.public)

    zorg = Tag(name="Zorg", slug="zorg")
    db.add(zorg)
    db.flush()
    pa.tags = [zorg]
    pb.tags = [zorg]
    db.flush()
    tool_service.set_tools(db, pa, "Claude Code")
    tool_service.set_tools(db, pb, "Cursor")
    db.flush()

    # AND: zelfde tag, maar alleen Alfa heeft de tool.
    rows = members_service.list_public_profiles(db, tag="zorg", tool="claude")
    assert {p.display_name for p in rows} == {"Alfa"}


def test_members_blank_tool_filter_ignored(db, make_member, make_profile):
    a = make_member(email="bt@example.com", name="Iedereen")
    make_profile(a, visibility=Visibility.public)
    rows = members_service.list_public_profiles(db, tool="   ")
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# AVG — profile_tool-koppelrijen weg na delete_member_completely               #
# --------------------------------------------------------------------------- #
def test_delete_member_removes_profile_tool_links_not_master(
    db, make_member, make_profile
):
    from app.services import account_deletion

    a = make_member(email="da@example.com", name="Te Wissen")
    pa = make_profile(a, visibility=Visibility.public)
    b = make_member(email="db@example.com", name="Blijft")
    pb = make_profile(b, visibility=Visibility.public)

    # Beide delen dezelfde gedeelde Tool-rij.
    tool_service.set_tools(db, pa, "Claude Code")
    tool_service.set_tools(db, pb, "Claude Code")
    db.flush()
    tool_id = db.scalar(select(Tool.id).where(Tool.slug == "claude-code"))
    assert tool_id is not None

    account_deletion.delete_member_completely(db, a)
    db.flush()

    # Koppelrijen van het gewiste profiel zijn weg...
    remaining = db.execute(
        select(profile_tool.c.profile_id, profile_tool.c.tool_id)
    ).all()
    assert (pa.id, tool_id) not in remaining
    # ...maar de koppeling van het andere lid blijft, en de master-rij óók.
    assert (pb.id, tool_id) in remaining
    assert db.get(Tool, tool_id) is not None


# --------------------------------------------------------------------------- #
# _cosmic_tools.html — logo-img vs. inline letter-tile-fallback                #
# --------------------------------------------------------------------------- #
def test_cosmic_tools_template_logo_and_initial_fallback():
    """Met logo_url → <img>; zonder → een letter-tile met de eerste letter."""
    from app.main import templates

    tmpl = templates.env.get_template("profiles/_cosmic_tools.html")
    with_logo = Tool(name="Cursor", slug="cursor", logo_url="/uploads/logo-x.webp")
    no_logo = Tool(name="n8n", slug="n8n")

    out_logo = tmpl.render(tools=[with_logo])
    assert 'class="tool-pill__logo"' in out_logo
    assert "/uploads/logo-x.webp" in out_logo
    assert "tool-pill__tile" not in out_logo

    out_init = tmpl.render(tools=[no_logo])
    assert 'class="tool-pill__tile"' in out_init
    assert ">N<" in out_init  # eerste letter, uppercased
    assert "tool-pill__logo" not in out_init
