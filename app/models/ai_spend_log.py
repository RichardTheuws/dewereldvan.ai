"""AiSpendLog — append-only kasboek van élke betaalde niet-lid-AI-call.

Dit is de enige plek waar bezoeker-AI-uitgaven worden geboekt; léden-acties
schrijven hier NIET (die lopen via het bestaande, ongelimiteerde lid-pad), zodat
de €50-weektelling per definitie alleen "gewone bezoekers" omvat (doc §2.1/§4.1).

Eén rij per call, met de **echte** token-usage uit ``response.usage``. De kost
wordt bevroren in ``cost_eur_micros`` (tokens × modelprijs op het moment van de
call), zodat een latere prijswijziging oude rijen niet vervalst. Bij een
cache-hit telt de rij wel mee als call maar kost €0 (``cost_eur_micros = 0``,
``cache_hit = True``).

Append-only: geen update, geen delete. De dag/IP/week-tellingen lezen dit met de
rij-tel/SUM-patronen uit ``app.services.magic_link`` (glijdend venster). Bewust
géén ``member_id`` (de telunit is de signed-cookie ``visitor_id``, niet een lid).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiSpendLog(Base):
    __tablename__ = "ai_spend_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Signed-cookie bezoeker (geen member_id). Telunit voor de per-bezoeker
    # daglimiet → index voor de rij-tel-query.
    visitor_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # Echte client-IP (CF-Connecting-IP) — grover vangnet voor de per-IP
    # daglimiet. "unknown" als de header ontbreekt (faal-veilig, doc §risico 3).
    ip: Mapped[str] = mapped_column(String(45), index=True, nullable=False)
    # 'url_card' | 'concierge_q' | 'tool_explain' — vrije string (geen DB-enum,
    # spiegelt de DiscoveryRun.status-aanpak; de geldige waarden leven in
    # visitor_spend.CONCEPTS).
    concept: Mapped[str] = mapped_column(String(16), nullable=False)
    # Hash van (concept, genormaliseerde input) — voor de identieke-prompt-cache
    # en dedup. Index zodat de cache-lookup goedkoop is.
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Bevroren kost in micro-euro (1 EUR = 1_000_000): tokens × modelprijs op het
    # moment van de call. Integer → geen float-drift in de weeksom.
    cost_eur_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # True = uit cache geserveerd; dan is cost_eur_micros = 0 (telt als call,
    # niet als uitgave).
    cache_hit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # De gegenereerde uitkomst (gestreamde tekst/HTML van de call), zodat een
    # identieke-prompt-cache-hit (Fase 2) de eerdere uitkomst kan hér-serveren
    # zonder nieuwe call. Nullable: niet elke rij hoeft inhoud te bewaren.
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # Glijdend venster voor de dag/week-tellingen; index voor de COUNT/SUM-queries.
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), index=True, nullable=False
    )
