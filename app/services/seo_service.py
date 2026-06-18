"""SEO-service (L4) — canonical URLs, JSON-LD, sitemap-entries.

Levert de structured-data en sitemap-bouwstenen voor de publieke pagina's:

- ``canonical_url(path)``       : absolute canonical op basis van ``BASE_URL``.
- ``absolute_url(url)``         : maakt een (mogelijk relatieve) media-URL
  absoluut voor OG/JSON-LD (relatieve ``/uploads/..`` foto's krijgen de host).
- ``jsonld_person(profile)``    : schema.org ``Person`` voor een publiek lid.
- ``jsonld_project(offering)``  : ``SoftwareApplication`` (als er een externe
  URL is) of ``CreativeWork`` voor een publiek project.
- ``sitemap_entries(db)``       : publieke personen + projecten met ``lastmod``.

Poort: alleen content die ``can_view(.., viewer=None)`` zou tonen verschijnt in
de sitemap en krijgt JSON-LD; besloten/geschorst → geen entry, geen datalek in
unfurls (spiegelt ``is_noindex``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    Member,
    MemberStatus,
    Offering,
    Profile,
    Visibility,
)

__all__ = [
    "SitemapEntry",
    "canonical_url",
    "absolute_url",
    "jsonld_person",
    "jsonld_project",
    "sitemap_entries",
]


@dataclass(frozen=True)
class SitemapEntry:
    """Eén sitemap-regel: absolute ``loc`` + optionele ``lastmod`` (ISO-datum)."""

    loc: str
    lastmod: str | None = None


def _base() -> str:
    """``BASE_URL`` zonder trailing slash (stabiele join-basis)."""
    return settings.base_url.rstrip("/")


def canonical_url(path: str) -> str:
    """Bouw een absolute canonical URL voor een interne ``path`` (``/leden/x``)."""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{_base()}{path}"


def absolute_url(url: str | None) -> str | None:
    """Maak een media-URL absoluut voor OG/JSON-LD.

    Al-absolute (``http(s)://``) of scheme-relatieve (``//host``) URLs blijven
    ongemoeid; een interne ``/uploads/..``/relatieve URL krijgt ``BASE_URL``
    ervoor. ``None``/leeg → ``None``.
    """
    if not url:
        return None
    u = url.strip()
    if not u:
        return None
    if u.startswith(("http://", "https://", "//")):
        return u
    if not u.startswith("/"):
        u = f"/{u}"
    return f"{_base()}{u}"


def _is_public(profile: Profile) -> bool:
    """``can_view(profile, viewer=None)`` voor anonieme bezoekers (poort-spiegel)."""
    owner = profile.member
    return (
        profile.visibility == Visibility.public
        and owner is not None
        and owner.status == MemberStatus.approved
    )


def _person_url(profile: Profile) -> str:
    return canonical_url(f"/leden/{profile.slug}")


def _project_url(offering: Offering) -> str:
    return canonical_url(f"/projecten/{offering.slug}")


def _lastmod(value: datetime | None) -> str | None:
    return value.date().isoformat() if value is not None else None


# --- JSON-LD ---------------------------------------------------------------


def jsonld_person(profile: Profile) -> dict:
    """schema.org ``Person`` voor een publiek profiel.

    ``image`` = absolute foto (geüpload of AI-cover), ``knowsAbout`` = tags,
    ``makesOffer`` = publieke projecten (met stabiele project-URL). Velden zonder
    waarde worden weggelaten zodat de JSON-LD schoon blijft.
    """
    data: dict = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": profile.display_name,
        "url": _person_url(profile),
    }
    description = profile.headline or profile.bio
    if description:
        data["description"] = description

    image = absolute_url(profile.photo_url or profile.cover_image_url)
    if image:
        data["image"] = image

    tags = [t.name for t in getattr(profile, "tags", []) if t.name]
    if tags:
        data["knowsAbout"] = tags

    offers = []
    for off in getattr(profile, "offerings", []):
        if not off.slug:
            continue
        item: dict = {"@type": "CreativeWork", "name": off.title, "url": _project_url(off)}
        offers.append({"@type": "Offer", "itemOffered": item})
    if offers:
        data["makesOffer"] = offers

    return data


def jsonld_project(offering: Offering) -> dict:
    """schema.org ``SoftwareApplication`` (externe URL aanwezig) of ``CreativeWork``.

    ``url`` wijst naar de échte externe site als die er is; ``image`` = absolute
    ``image_url``; ``author`` = ``Person`` (de maker, met link naar de leden-
    pagina). Lege velden worden weggelaten.
    """
    ext = absolute_url(offering.url)
    data: dict = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication" if ext else "CreativeWork",
        "name": offering.title,
        "url": ext or _project_url(offering),
    }
    if data["@type"] == "SoftwareApplication":
        # Een generieke, veilige default-categorie; verfijnbaar zonder de shape
        # te breken (tests asserten alleen de verplichte keys).
        data["applicationCategory"] = "WebApplication"

    if offering.description:
        data["description"] = offering.description

    image = absolute_url(offering.image_url)
    if image:
        data["image"] = image

    profile = offering.profile
    if profile is not None:
        data["author"] = {
            "@type": "Person",
            "name": profile.display_name,
            "url": _person_url(profile),
        }
    return data


# --- Sitemap ---------------------------------------------------------------


def sitemap_entries(db: Session) -> list[SitemapEntry]:
    """Alle PUBLIEKE personen + hun publieke projecten, voor ``/sitemap.xml``.

    Sluit besloten/geschorst uit via dezelfde poort als ``can_view(anon)``
    (``visibility=public`` + eigenaar ``approved``). Personen eerst, daarna hun
    projecten met een stabiele slug; ``lastmod`` = ``updated_at``-datum.
    """
    stmt = (
        select(Profile)
        .join(Member, Profile.member_id == Member.id)
        .where(
            Profile.visibility == Visibility.public,
            Member.status == MemberStatus.approved,
        )
        .order_by(Profile.display_name.asc(), Profile.id.asc())
        .options(
            selectinload(Profile.member),
            selectinload(Profile.offerings),
        )
    )
    profiles = list(db.scalars(stmt).unique().all())

    entries: list[SitemapEntry] = []
    for profile in profiles:
        if not _is_public(profile):  # defensief; query dekt dit al
            continue
        entries.append(
            SitemapEntry(
                loc=_person_url(profile),
                lastmod=_lastmod(getattr(profile, "updated_at", None)),
            )
        )
        for off in sorted(profile.offerings, key=lambda o: o.position):
            if not off.slug:
                continue
            entries.append(
                SitemapEntry(
                    loc=_project_url(off),
                    lastmod=_lastmod(getattr(off, "updated_at", None)),
                )
            )
    return entries
