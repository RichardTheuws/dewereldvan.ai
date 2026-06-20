"""Seed — bekende AI-tools in de ``tool``-catalogus (idempotent, niet-destructief).

Spiegelt de seed-conventie van 0011 (agenda/roadmap): per tool wordt alleen
ingevoegd als de canonieke ``slug`` nog NIET bestaat — zo overschrijven we nooit
een door een lid vrij toegevoegde of later verrijkte tool, en is een herhaalde
stamp veilig. ``logo_url`` blijft leeg (lazy/best-effort later via de
tool-service). De ``slug`` is exact ``security.slugify(name)`` zodat de service
(``tool_service.get_or_create``) tegen deze rijen dedupt i.p.v. duplicaten te maken.

Prod-data-migratie: de testsuite bouwt via ``create_all`` (niet via Alembic), dus
deze seed raakt de SQLite-suite niet; de Postgres-pariteitstest draait 'm wél.

Revision ID: 0018_seed_tools
Revises: 0017_tool_profile_tool
Create Date: 2026-06-20

"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_seed_tools"
down_revision: str | None = "0017_tool_profile_tool"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Lokale slug-kopie (identiek aan ``app.security.slugify``) zodat de migratie geen
# app-code importeert (migraties moeten stand-alone reproduceerbaar zijn).
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", ascii_only.lower()).strip("-")
    return slug or "lid"


# (naam, url) — gegronde, bekende AI-tools. logo_url leeg (lazy/best-effort later).
_TOOLS: list[tuple[str, str]] = [
    ("Claude Code", "https://claude.com/claude-code"),
    ("Claude", "https://claude.ai"),
    ("Cursor", "https://cursor.com"),
    ("Windsurf", "https://windsurf.com"),
    ("GitHub Copilot", "https://github.com/features/copilot"),
    ("ChatGPT", "https://chatgpt.com"),
    ("Perplexity", "https://www.perplexity.ai"),
    ("Obsidian", "https://obsidian.md"),
    ("Gemini", "https://gemini.google.com"),
    ("v0", "https://v0.dev"),
    ("Replit", "https://replit.com"),
    ("Bolt", "https://bolt.new"),
    ("Lovable", "https://lovable.dev"),
    ("LangChain", "https://www.langchain.com"),
    ("LlamaIndex", "https://www.llamaindex.ai"),
    ("Ollama", "https://ollama.com"),
    ("LM Studio", "https://lmstudio.ai"),
    ("n8n", "https://n8n.io"),
    ("Zapier", "https://zapier.com"),
    ("Midjourney", "https://www.midjourney.com"),
    ("ElevenLabs", "https://elevenlabs.io"),
    ("Whisper", "https://openai.com/research/whisper"),
    ("Hugging Face", "https://huggingface.co"),
    ("Pinecone", "https://www.pinecone.io"),
    ("Supabase", "https://supabase.com"),
    ("Vercel", "https://vercel.com"),
    ("Linear", "https://linear.app"),
    ("Notion", "https://www.notion.so"),
    ("Raycast", "https://www.raycast.com"),
    ("Warp", "https://www.warp.dev"),
]


_tool = sa.table(
    "tool",
    sa.column("name", sa.String),
    sa.column("slug", sa.String),
    sa.column("url", sa.String),
)


def upgrade() -> None:
    bind = op.get_bind()

    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT slug FROM tool")).fetchall()
    }

    rows = []
    for name, url in _TOOLS:
        slug = _slugify(name)
        if slug in existing:
            continue  # niet overschrijven (idempotent + niet-destructief)
        existing.add(slug)
        rows.append({"name": name, "slug": slug, "url": url})

    if rows:
        op.bulk_insert(_tool, rows)


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [_slugify(name) for name, _ in _TOOLS]
    # Verwijder alleen de gezaaide rijen die nog GEEN profiel-koppeling hebben,
    # zodat een lid-gekoppelde (of vrij toegevoegde) tool niet sneuvelt.
    bind.execute(
        sa.text(
            "DELETE FROM tool WHERE slug IN :slugs "
            "AND id NOT IN (SELECT tool_id FROM profile_tool)"
        ).bindparams(sa.bindparam("slugs", value=slugs, expanding=True))
    )
