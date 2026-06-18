"""Emphasis-service (L1) — layout-prominentie zetten/normaliseren.

``profile.emphasis`` (person | projects | balanced, default balanced) stuurt of
de foto/headline/bio groot komt (``person``), de projectkaarten-met-beeld groot
komen (``projects``), of alles gelijk blijft (``balanced``). Gevraagd in de
AI-bouwflow én bewerkbaar op de profielpagina; beide routes komen via één
endpoint hier binnen.

Geen JS-logica: de waarde mapt in de template op een ``.emphasis-*``-class.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Profile, ProfileEmphasis

__all__ = ["parse_emphasis", "set_emphasis", "emphasis_class"]


def parse_emphasis(value: str | ProfileEmphasis | None) -> ProfileEmphasis:
    """Normaliseer ruwe input naar een geldige ``ProfileEmphasis``.

    Onbekende/lege waarden vallen veilig terug op ``balanced`` (de default), zodat
    een gemanipuleerde of ontbrekende form-waarde nooit een fout oplevert.
    """
    if isinstance(value, ProfileEmphasis):
        return value
    if not value:
        return ProfileEmphasis.balanced
    try:
        return ProfileEmphasis(str(value).strip().lower())
    except ValueError:
        return ProfileEmphasis.balanced


def set_emphasis(
    db: Session, profile: Profile, value: str | ProfileEmphasis | None
) -> ProfileEmphasis:
    """Zet ``profile.emphasis`` (genormaliseerd) en flush; retourneert de waarde.

    Idempotent: gelijke waarde laat de rij ongemoeid maar geeft de huidige
    waarde terug, zodat de route altijd de juiste keuze-staat kan herrenderen.
    """
    emphasis = parse_emphasis(value)
    if profile.emphasis != emphasis:
        profile.emphasis = emphasis
        db.flush()
    return profile.emphasis


def emphasis_class(profile: Profile) -> str:
    """De CSS-modifier-class voor de huidige emphasis (``emphasis-person`` etc.).

    Eén bron van waarheid voor profielpagina én ledenkaart; geen logica in de
    template behalve het plakken van deze class op de sectiewrapper.
    """
    emphasis = profile.emphasis or ProfileEmphasis.balanced
    return f"emphasis-{emphasis.value}"
