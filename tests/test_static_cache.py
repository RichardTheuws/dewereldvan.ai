"""Cache-headers op /static.

Zonder expliciete Cache-Control cachet Cloudflare alleen zijn default-extensies
(css/js/beelden); de intro-GLB (1.8MB, ``app/static/models/``) ging daardoor voor
élke bezoeker opnieuw door de tunnel (14-60s) en de 3D-act haalde zijn
2.5s-mount-gate nooit. Alle /static-links busten al met ``?v={{ asset_ver }}``,
dus immutable + lange max-age is veilig.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_IMMUTABLE = "public, max-age=31536000, immutable"


def _client() -> TestClient:
    from app.main import app

    return TestClient(app, base_url="https://testserver")


def test_static_css_carries_immutable_cache_control():
    resp = _client().get("/static/cosmic.css")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == _IMMUTABLE


def test_intro_glb_carries_immutable_cache_control():
    resp = _client().get("/static/models/wereld-van-ai.glb")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == _IMMUTABLE


def test_static_response_carries_no_session_cookie():
    # Set-Cookie op statics blokkeert edge-caching en is functioneel zinloos.
    resp = _client().get("/static/cosmic.css")
    assert resp.status_code == 200
    assert "set-cookie" not in resp.headers


def test_dynamic_route_not_cache_locked():
    resp = _client().get("/healthz")
    assert resp.status_code == 200
    assert "immutable" not in (resp.headers.get("cache-control") or "")
