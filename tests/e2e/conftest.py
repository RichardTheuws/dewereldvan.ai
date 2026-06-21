"""Browser-UAT (Laag 3) — fixtures: een ECHTE app-instance + Playwright.

Dit is wat TestClient niet kan: JS/htmx/SSE/canvas/motion draaien in een echte
browser. We starten ``app.main:app`` als uvicorn-subprocess tegen een geseede
SQLite-DB (publieke makers + project), met AI UIT (geen kosten, geen netwerk), en
geven de browser de live base-URL. Alleen via ``pytest -m e2e`` (uit de snelle suite).

Vereist: ``pip install -r requirements-e2e.txt`` + ``playwright install chromium``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

_SECRET = "e2e-secret-key-deterministic-0123456789abcdef"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed(db_url: str) -> None:
    """Maak schema + seed publieke makers (gedeelde tags/tools → constellatie-lijnen)
    en één project met slug. In-proces, vóór de server start."""
    os.environ.setdefault("SECRET_KEY", _SECRET)
    os.environ.setdefault("EMAIL_BACKEND", "console")
    os.environ.setdefault("DATABASE_URL", db_url)
    from app.models import (
        Base,
        Member,
        MemberStatus,
        Offering,
        Profile,
        Tag,
        Tool,
        Visibility,
    )
    from app.services import offering_slug
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        tags = {k: Tag(slug=k, name=k) for k in ("voice-agents", "rag", "zorg")}
        tools = {k: Tool(slug=k, name=k.title()) for k in ("cursor", "claude-code")}
        s.add_all(list(tags.values()) + list(tools.values()))
        s.flush()
        makers = [
            ("Lena Hart", "lena-hart", ["voice-agents", "zorg"], ["cursor"]),
            ("Bram de Vries", "bram-de-vries", ["rag", "voice-agents"], ["cursor", "claude-code"]),
            ("Senna Ali", "senna-ali", ["voice-agents"], ["claude-code"]),
            ("Tycho Berg", "tycho-berg", ["rag"], []),
            ("Iris Pool", "iris-pool", ["zorg"], ["cursor"]),
        ]
        first_profile = None
        for name, slug, tg, tl in makers:
            m = Member(email=f"{slug}@e2e.test", name=name, status=MemberStatus.approved)
            s.add(m)
            s.flush()
            p = Profile(
                member_id=m.id, slug=slug, display_name=name,
                visibility=Visibility.public, headline=f"Bouwt {tg[0]}-dingen",
                makes_summary=f"Werkt aan {tg[0]}.",
            )
            for t in tg:
                p.tags.append(tags[t])
            for t in tl:
                p.tools.append(tools[t])
            s.add(p)
            s.flush()
            if first_profile is None:
                first_profile = p
        off = Offering(title="E2E Project", position=0)
        first_profile.offerings.append(off)
        s.flush()
        offering_slug.ensure_slug(s, off)
        s.commit()
    engine.dispose()


@pytest.fixture(scope="session")
def live_server():
    """Start de echte app (uvicorn) tegen een geseede SQLite-DB, AI uit."""
    tmp = tempfile.mkdtemp(prefix="dwv-e2e-")
    db_file = Path(tmp) / "e2e.db"
    db_url = f"sqlite+pysqlite:///{db_file}"
    _seed(db_url)

    port = _free_port()
    env = {
        **os.environ,
        "SECRET_KEY": _SECRET,
        "EMAIL_BACKEND": "console",
        "CONSOLE_EMAIL_DIR": str(Path(tmp) / "outbox"),
        "DATABASE_URL": db_url,
        "ADMIN_EMAILS": "admin@dewereldvan.ai",
        "AI_ENRICH_ENABLED": "false",
        "BASE_URL": f"http://127.0.0.1:{port}",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode() if proc.stdout else ""
            raise RuntimeError(f"uvicorn stopte voortijdig:\n{out}")
        try:
            if httpx.get(base + "/", timeout=2).status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(0.4)
    if not ready:
        proc.terminate()
        raise RuntimeError("uvicorn werd niet op tijd bereikbaar")
    try:
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
