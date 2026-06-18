"""HTTP-laag voor de profielfoto-upload (L1) — de échte multipart-grens.

De service-tests (``test_photo_service.py``) roepen ``store_member_photo`` direct
aan en gaan dus nooit door Starlette's multipart-parser. Deze suite dekt juist die
laag: zonder een expliciete ``max_part_size`` zou Starlette's 1 MB-default elke
upload >1 MB kappen vóór de route draait, waardoor de gedocumenteerde 6 MB-cap
onbereikbaar is. Bewijst hier:

- een geldige foto tussen 1 en 6 MB slaagt (de 1 MB-default is gelift), en
- een part > 6 MB valt in dezelfde vriendelijke NL-400 i.p.v. een rauwe
  framework-exception.

Volledig in-memory: throwaway engine, ``current_member`` override, Pillow-bytes.
"""

from __future__ import annotations

import re
from io import BytesIO

import pytest
from app.config import settings
from app.models import Base, Member, MemberStatus
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def route_engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def SessionTest(route_engine):
    return sessionmaker(bind=route_engine, autoflush=False, future=True)


@pytest.fixture
def approved_id(SessionTest):
    s = SessionTest()
    m = Member(
        email="shooter@example.com", name="Foto Graaf", status=MemberStatus.approved
    )
    s.add(m)
    s.commit()
    mid = m.id
    s.close()
    return mid


@pytest.fixture
def client(route_engine, SessionTest, approved_id):
    from app.db import get_db
    from app.deps import current_member
    from app.main import app
    from fastapi import Depends
    from sqlalchemy.orm import Session

    def _override_get_db():
        db = SessionTest()
        try:
            yield db
        finally:
            db.close()

    def _override_current_member(db: Session = Depends(get_db)):
        return db.get(Member, approved_id)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[current_member] = _override_current_member
    try:
        yield TestClient(app, base_url="https://testserver")
    finally:
        app.dependency_overrides.clear()


def _csrf(client: TestClient) -> str:
    page = client.get("/profiel/ai/bouwen")
    assert page.status_code == 200
    m = re.search(
        r'X-CSRF-Token"?\s*:\s*"?([A-Za-z0-9_\-]+)', page.text
    ) or re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert m, "CSRF token not found on build page"
    return m.group(1)


def _noise_png(target_bytes: int) -> bytes:
    """Een geldige (decodeerbare) PNG van ~``target_bytes`` bytes.

    Ruis-pixels comprimeren nauwelijks, dus de PNG-grootte ligt dicht bij de
    onbewerkte pixel-bytes (w*h*3). We kiezen de afmeting daarop en groeien alleen
    als we (door toeval) onder de drempel uitkomen — zo blijft de payload netjes in
    de bedoelde band i.p.v. fors te overschieten.
    """
    import math
    import os

    side = max(64, int(math.sqrt(target_bytes / 3)))
    while True:
        img = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
        buf = BytesIO()
        img.save(buf, format="PNG")
        data = buf.getvalue()
        if len(data) >= target_bytes:
            return data
        side = int(side * 1.1) + 1


def test_upload_between_1mb_and_6mb_succeeds(client):
    """Een ~2 MB foto (boven Starlette's 1 MB-default) moet de route bereiken."""
    token = _csrf(client)
    payload = _noise_png(2 * 1024 * 1024)
    assert 1 * 1024 * 1024 < len(payload) < settings.max_upload_bytes
    resp = client.post(
        "/profiel/foto",
        headers={"X-CSRF-Token": token},
        files={"file": ("vakantie.png", payload, "image/png")},
    )
    assert resp.status_code == 200
    # Geen lekkende framework-fout, en geen foutmelding in het fragment.
    assert "te groot" not in resp.text


def test_upload_over_6mb_returns_friendly_400(client):
    """Een part > 6 MB valt in de vriendelijke NL-400, geen rauwe MultiPartException."""
    token = _csrf(client)
    payload = _noise_png(settings.max_upload_bytes + 512 * 1024)
    assert len(payload) > settings.max_upload_bytes
    resp = client.post(
        "/profiel/foto",
        headers={"X-CSRF-Token": token},
        files={"file": ("enorm.png", payload, "image/png")},
    )
    assert resp.status_code == 400
    assert "te groot" in resp.text
    # Geen lekkende interne framework-details.
    assert "Part exceeded maximum size" not in resp.text
