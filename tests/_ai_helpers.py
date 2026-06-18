"""Reusable test doubles for AI-native profielbouw (no network, no cost).

Importable from any test module as ``from tests._ai_helpers import ...``. Kept
out of ``conftest`` so the classes can be imported directly (conftest is loaded
by pytest as a plugin, not as a normal importable module across the package).
"""

from __future__ import annotations

import contextlib

from app.ai.base import GeneratedImage


# --- Fake AI cover-image backend ---------------------------------------------
class FakeImageGenerator:
    """In-memory ImageGenerator that records prompts (no network, no cost).

    - ``fail=False`` (default): returns a deterministic fake cover URL.
    - ``fail=True``: returns ``GeneratedImage(url=None)`` to exercise the graceful
      "cover failed, profile still works" fallback the route must tolerate.
    """

    URL = "https://img.test/cover.png"

    def __init__(self, *, fail: bool = False) -> None:
        self.prompts: list[str] = []
        self.fail = fail

    def generate(self, prompt: str) -> GeneratedImage:
        self.prompts.append(prompt)
        if self.fail:
            return GeneratedImage(url=None)
        return GeneratedImage(url=self.URL)


# --- Anthropic mocking helpers -----------------------------------------------
class _FakeMessage:
    """Stand-in for an Anthropic ``Message`` (only what the service reads)."""

    def __init__(self, *, stop_reason: str = "end_turn", content=None) -> None:
        self.stop_reason = stop_reason
        self.content = content if content is not None else []


class _FakeStream:
    """Context-manager mirroring ``client.messages.stream(...)``.

    Yields ``text_stream`` chunks and returns a final ``_FakeMessage`` from
    ``get_final_message()``. A list of ``stop_reason``s lets a test drive the
    ``pause_turn`` server-tool-loop (one entry consumed per ``stream(...)`` call).
    """

    def __init__(self, owner: FakeAnthropic) -> None:
        self._owner = owner

    def __enter__(self) -> _FakeStream:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    @property
    def text_stream(self):
        return iter(self._owner.deltas)

    def get_final_message(self) -> _FakeMessage:
        owner = self._owner
        if owner.stream_stop_reasons:
            idx = min(owner.stream_calls, len(owner.stream_stop_reasons) - 1)
            stop = owner.stream_stop_reasons[idx]
        else:
            stop = "end_turn"
        owner.stream_calls += 1
        return _FakeMessage(stop_reason=stop, content=owner.assistant_content)


class _FakeParseResponse:
    def __init__(self, parsed_output, stop_reason: str = "end_turn") -> None:
        self.parsed_output = parsed_output
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, owner: FakeAnthropic) -> None:
        self._owner = owner

    def stream(self, **kwargs):
        self._owner.stream_kwargs.append(kwargs)
        return _FakeStream(self._owner)

    def parse(self, **kwargs):
        self._owner.parse_kwargs.append(kwargs)
        return _FakeParseResponse(
            self._owner.parsed_output, self._owner.parse_stop_reason
        )


class FakeAnthropic:
    """A drop-in for ``anthropic.Anthropic`` — no real client is ever built.

    Configure the streaming + structured-output behaviour via the constructor;
    inspect ``stream_kwargs`` / ``parse_kwargs`` to assert that forbidden params
    (temperature/top_p/budget_tokens) are never sent and that ``thinking`` is.
    """

    def __init__(
        self,
        *,
        deltas: list[str] | None = None,
        stream_stop_reasons: list[str] | None = None,
        assistant_content=None,
        parsed_output=None,
        parse_stop_reason: str = "end_turn",
    ) -> None:
        self.deltas = deltas if deltas is not None else ["Hoi ", "daar."]
        self.stream_stop_reasons = stream_stop_reasons or []
        self.assistant_content = (
            assistant_content
            if assistant_content is not None
            else [{"type": "text", "text": "".join(self.deltas)}]
        )
        self.parsed_output = parsed_output
        self.parse_stop_reason = parse_stop_reason

        self.stream_calls = 0
        self.stream_kwargs: list[dict] = []
        self.parse_kwargs: list[dict] = []
        self.messages = _FakeMessages(self)


@contextlib.contextmanager
def install_fake_anthropic(monkeypatch, fake: FakeAnthropic):
    """Patch ``anthropic.Anthropic`` so the service builds ``fake`` instead.

    The service constructs its client lazily via ``anthropic.Anthropic()``; we
    replace that callable so no API key is required and no network is touched.
    """
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", lambda *a, **k: fake)
    yield fake
