"""Import-smoke: every AI-native profielbouw module imports cleanly and the
routes are mounted. Guards against an accidental import-time API-key/network
dependency (the Anthropic client must be constructed lazily).
"""

from __future__ import annotations


def test_ai_modules_import():
    import app.ai  # noqa: F401
    import app.ai.base  # noqa: F401
    import app.ai.fal_generator  # noqa: F401
    import app.ai.noop_generator  # noqa: F401
    import app.routers.ai_profile  # noqa: F401
    import app.schemas.ai_profile  # noqa: F401
    import app.services.ai_conversation  # noqa: F401
    import app.services.ai_profile  # noqa: F401


def test_ai_service_import_does_not_require_api_key(monkeypatch):
    """Importing the service must not construct a client (no ANTHROPIC_API_KEY).

    The client is built lazily inside ``_client()``; merely importing the module
    (already done at collection time, even with no key set) must succeed. We do
    NOT ``importlib.reload`` here on purpose — reloading would mint fresh copies
    of EnrichmentRefused / DraftProfileOut and break ``isinstance`` identity in
    sibling tests.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import app.services.ai_profile as svc

    assert callable(svc.stream_turn)
    assert callable(svc.finalize_draft)
    # The lazy client factory exists but is not invoked at import time.
    assert callable(svc._client)


def test_models_exported_from_package():
    from app.models import (
        AiChatTurn,
        Offering,
        ProfileLink,
        ProfileLinkKind,
    )

    assert ProfileLinkKind.affiliation.value == "affiliation"
    assert AiChatTurn.__tablename__ == "ai_chat_turn"
    assert ProfileLink.__tablename__ == "profile_link"
    assert hasattr(Offering, "url") and hasattr(Offering, "image_url")


def test_ai_routes_are_mounted():
    from app.main import app

    from tests._route_helpers import app_paths
    paths = app_paths(app)
    assert "/profiel/ai/bouwen" in paths
    assert "/profiel/ai/bericht" in paths
    assert "/profiel/ai/stream" in paths
    assert "/profiel/ai/maak-draft" in paths
    assert "/profiel/ai/cover" in paths
    assert "/profiel/ai/publiceren" in paths
    assert "/profiel/ai/opnieuw" in paths


def test_web_tools_scoped_to_member_domains():
    """web_fetch is constrained to the member's own links; web_search dropped."""
    from app.services.ai_profile import _member_domains, _web_tools

    msgs = [
        {"role": "user", "content": "Mijn site: https://acme.example/me ook http://foo.test/x"},
        {"role": "assistant", "content": [{"type": "text", "text": "http://evil.test"}]},
    ]
    # Domains come only from the member's own turns (not tool/assistant output).
    assert _member_domains(msgs) == ["acme.example", "foo.test"]

    tools = _web_tools(msgs)
    assert len(tools) == 1
    assert tools[0]["name"] == "web_fetch"
    assert tools[0]["allowed_domains"] == ["acme.example", "foo.test"]
    # No links pasted -> fall back to the unconstrained toolset.
    fallback = _web_tools([{"role": "user", "content": "geen links hier"}])
    assert any(t["name"] == "web_search" for t in fallback)


def test_safe_url_filter_blocks_dangerous_schemes():
    from app.main import safe_url

    assert safe_url("javascript:alert(1)") == ""
    assert safe_url("JaVaScRiPt:alert(1)") == ""
    assert safe_url("data:text/html,x") == ""
    assert safe_url("mailto:a@b.c") == ""
    assert safe_url(None) == ""
    assert safe_url("https://x.test/a") == "https://x.test/a"
    assert safe_url("/leden/foo") == "/leden/foo"
    assert safe_url("//cdn.test/a") == "//cdn.test/a"
