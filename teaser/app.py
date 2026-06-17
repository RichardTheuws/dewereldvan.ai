"""Minimale teaser-service voor dewereldvan.ai.

Serveert de statische teaser en vangt wachtlijst-aanmeldingen op in SQLite.
Bewust klein en throwaway: zodra het volledige platform op de M4 live gaat,
neemt dat de tunnel over en migreren we deze adressen naar de ledendatabase.
"""
import datetime
import os
import pathlib
import re
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

BASE = pathlib.Path(__file__).parent
DB = pathlib.Path(os.environ.get("WAITLIST_DB", BASE / "data" / "waitlist.db"))
DB.parent.mkdir(parents=True, exist_ok=True)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="dewereldvan.ai — teaser", docs_url=None, redoc_url=None)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS waitlist("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "email TEXT NOT NULL UNIQUE,"
        "created_at TEXT NOT NULL)"
    )
    return conn


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(BASE / "index.html")


@app.post("/api/waitlist")
async def waitlist(request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
    email = (data.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        return JSONResponse({"ok": False, "error": "invalid_email"}, status_code=422)
    conn = _db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO waitlist(email, created_at) VALUES (?, ?)",
            (email, datetime.datetime.now(datetime.UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"ok": True})
