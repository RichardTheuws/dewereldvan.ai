"""Browser-UAT (Laag 3) — verifieert de ECHTE ervaring in Chromium.

Draait alleen via ``pytest -m e2e``. Toetst wat de unit-suite per definitie niet
kan: dat de demo écht materialiseert, de constellatie rendert, htmx de concierge
opent, /demo afspeelt mét causaliteit — en dat er GEEN JavaScript-fouten optreden.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _collect_errors(page: Page) -> list[str]:
    """Vang console-errors én ongevangen page-excepties (de harde JS-vangst)."""
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    return errors


def _assert_no_js_errors(errors: list[str], where: str) -> None:
    # Negeer benigne netwerk-ruis (fonts/og-image kunnen in CI 404'en); echte
    # JS-excepties en script-fouten blijven hard falen.
    real = [e for e in errors if "net::" not in e and "favicon" not in e.lower()
            and "status of 404" not in e and "Failed to load resource" not in e]
    assert not real, f"JS-fouten op {where}:\n" + "\n".join(real)


# --------------------------------------------------------------------------- #
# W2 — de homepage-demo bouwt vóór je ogen                                      #
# --------------------------------------------------------------------------- #
def test_homepage_demo_materializes(live_server, page: Page):
    errors = _collect_errors(page)
    page.goto(live_server, wait_until="networkidle")
    demo = page.locator(".home-demo")
    expect(demo).to_be_visible()
    demo.scroll_into_view_if_needed()
    # De gescripte choreografie draait → een demo-step krijgt field--ready (alleen
    # door de JS gezet). Bewijst dat de materialisatie ECHT afspeelt.
    page.wait_for_selector(".home-demo .demo-step.field--ready", timeout=8000)
    # En het gematerialiseerde profiel is echt zichtbaar (opacity teruggezet).
    name = page.locator(".home-demo .display-name")
    expect(name).to_have_text("Lena Hart")
    opacity = name.evaluate("el => getComputedStyle(el.closest('.demo-step')).opacity")
    assert float(opacity) > 0.9, f"demo-step niet zichtbaar (opacity={opacity})"
    page.screenshot(path="tests/e2e/_home.png")
    _assert_no_js_errors(errors, "/")


# --------------------------------------------------------------------------- #
# W1 — echte makers-constellatie                                                #
# --------------------------------------------------------------------------- #
def test_homepage_constellation_renders_real_makers(live_server, page: Page):
    page.goto(live_server, wait_until="networkidle")
    page.locator("#makers").scroll_into_view_if_needed()
    stars = page.locator(".home-star")
    expect(stars.first).to_be_visible()
    assert stars.count() >= 3, f"te weinig sterren: {stars.count()}"
    # Echte maker-namen, niet anoniem.
    expect(page.locator(".home-star__name").first).not_to_be_empty()
    # Gegronde verbindingslijnen (gedeelde tags/tools → SVG <line>).
    assert page.locator(".home-constellation__links line").count() >= 1
    # De ster linkt naar een echt profiel.
    href = page.locator(".home-star").first.get_attribute("href")
    assert href and href.startswith("/leden/"), href
    page.screenshot(path="tests/e2e/_constellation.png", full_page=True)
    page.locator(".home-constellation").screenshot(path="tests/e2e/_constellation_el.png")


# --------------------------------------------------------------------------- #
# Proef-chips openen de concierge, voorgevuld (geen betaalde call)             #
# --------------------------------------------------------------------------- #
def test_homepage_chip_opens_concierge_prefilled(live_server, page: Page):
    page.goto(live_server, wait_until="networkidle")
    chip = page.locator(".home-chip").first
    chip.scroll_into_view_if_needed()
    expected = chip.get_attribute("data-concierge-prefill")
    chip.click()
    overlay = page.locator("#concierge-overlay")
    expect(overlay).to_be_visible()
    expect(page.locator("#concierge-input")).to_have_value(expected)


# --------------------------------------------------------------------------- #
# /demo — speelt af mét scan→veld-causaliteit                                   #
# --------------------------------------------------------------------------- #
def test_demo_plays_with_causality(live_server, page: Page):
    errors = _collect_errors(page)
    page.goto(live_server + "/demo", wait_until="networkidle")
    page.locator("[data-demo-play]").click()
    page.wait_for_selector(".demo-step.field--ready", timeout=8000)
    expect(page.locator(".display-name")).to_have_text("Nova Belmonte")
    # De causaliteit-regels verschijnen synchroon (data-demo-reasons gevuld).
    page.wait_for_selector("[data-demo-reasons] .fetch-line", timeout=8000)
    page.screenshot(path="tests/e2e/_demo.png", full_page=True)
    _assert_no_js_errors(errors, "/demo")


# --------------------------------------------------------------------------- #
# /leden — verbonden graaf (kaarten + graaf-graad)                             #
# --------------------------------------------------------------------------- #
def test_leden_shows_connected_cards(live_server, page: Page):
    errors = _collect_errors(page)
    page.goto(live_server + "/leden", wait_until="networkidle")
    cards = page.locator(".member-star")
    expect(cards.first).to_be_visible()
    assert cards.count() >= 3
    # Het verbindings-signaal (graaf-graad) staat op minstens één kaart.
    assert page.locator(".member-star__bond").count() >= 1
    page.screenshot(path="tests/e2e/_leden.png", full_page=True)
    _assert_no_js_errors(errors, "/leden")


# --------------------------------------------------------------------------- #
# /proef — rendert zonder JS-fouten (AI uit → veilige default-staat)           #
# --------------------------------------------------------------------------- #
def test_proef_renders_without_js_errors(live_server, page: Page):
    errors = _collect_errors(page)
    page.goto(live_server + "/proef", wait_until="networkidle")
    expect(page.locator("body.cosmic")).to_be_visible()
    _assert_no_js_errors(errors, "/proef")


def _member_session_cookie(member_id: int) -> str:
    """Signeer een sessie-cookie zoals Starlette's SessionMiddleware (zelfde
    _SECRET als de conftest), zodat de browser als ingelogd lid laadt."""
    import base64
    import json

    import itsdangerous
    from tests.e2e.conftest import _SECRET

    raw = base64.b64encode(json.dumps({"member_id": member_id}).encode())
    return itsdangerous.TimestampSigner(_SECRET).sign(raw).decode()


def test_member_lands_in_canvas_agent_shell(live_server, page: Page):
    """Wat een INGELOGD lid op / ziet: de agent-canvas (dual-shell), niet de
    publieke kopstuk-voordeur. Verifieert dat 'ie rendert + de suggestie-chips
    laden + geen JS-fouten — exact het scherm dat Richard dagelijks ziet."""
    errors = _collect_errors(page)
    page.context.add_cookies([{
        "name": "session", "value": _member_session_cookie(1),
        "domain": "127.0.0.1", "path": "/",
    }])
    page.goto(live_server + "/", wait_until="networkidle")
    expect(page.locator("#canvas-form")).to_be_visible()
    expect(page.locator(".canvas-intro .headline")).to_contain_text("Welkom")
    # De contextuele suggestie-chips laden (hx-get /concierge/chips on load).
    page.wait_for_selector("#canvas-suggesties a, #canvas-suggesties button", timeout=6000)
    # Ambient ruststaat: de levende graaf landt óók voor het lid (niet leeg).
    ambient = page.locator("#canvas-ambient")
    expect(ambient).to_be_visible()
    assert page.locator("#canvas-ambient .home-star").count() >= 3
    ambient.scroll_into_view_if_needed()
    ambient.screenshot(path="tests/e2e/_canvas_ambient.png")
    page.screenshot(path="tests/e2e/_member_canvas.png", full_page=True)
    _assert_no_js_errors(errors, "/ (member canvas)")
