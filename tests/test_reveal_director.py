"""Reveal-invariant — elke kosmische pagina met ``data-reveal`` moet de
reveal-director laden, anders blijft de pagina blanco/onzichtbaar.

Achtergrond: ``.cosmic [data-reveal]`` start op ``opacity:0`` en wordt pas
zichtbaar als ``body.ready`` (of ``.is-in``) gezet wordt. Dat doet uitsluitend
``ai/_cosmic_canvas.html`` (de reveal-director). Een volledige cosmic-pagina die
``data-reveal`` gebruikt maar die director NIET include, rendert met JS aan een
lege pagina (de ``<noscript>``-fallback dekt alleen JS-uít). Dit is precies de
bug die /profiel/verbind en de AVG-afscheidspagina trof.

Deze test scant de templates statisch zodat de invariant geldt ongeacht route,
auth of zichtbaarheid — en nieuwe pagina's automatisch worden afgedwongen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
_DIRECTOR = 'include "ai/_cosmic_canvas.html"'
# De director-file zelf bevat `data-reveal` (in de querySelector) en `document.body`.
_SELF = "ai/_cosmic_canvas.html"


def _full_cosmic_pages_with_reveal() -> list[Path]:
    pages = []
    for path in _TEMPLATES.rglob("*.html"):
        rel = path.relative_to(_TEMPLATES).as_posix()
        if rel == _SELF:
            continue
        text = path.read_text(encoding="utf-8")
        # Alleen volledige documenten (eigen <body>); fragmenten erven de director.
        if "<body" not in text:
            continue
        if "data-reveal" not in text:
            continue
        pages.append(path)
    return pages


def test_found_cosmic_pages():
    """Sanity: de scan vindt daadwerkelijk pagina's (anders is de test loos)."""
    assert _full_cosmic_pages_with_reveal(), "geen cosmic data-reveal-pagina's gevonden"


@pytest.mark.parametrize(
    "page",
    _full_cosmic_pages_with_reveal(),
    ids=lambda p: p.relative_to(_TEMPLATES).as_posix(),
)
def test_reveal_pages_include_director(page: Path):
    text = page.read_text(encoding="utf-8")
    assert _DIRECTOR in text, (
        f"{page.relative_to(_TEMPLATES).as_posix()} gebruikt data-reveal maar include "
        f"ai/_cosmic_canvas.html niet → pagina blijft onzichtbaar met JS aan."
    )
