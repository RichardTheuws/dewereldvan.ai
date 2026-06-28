"""Ops-melding naar de admins via Telegram — voor unattended scripts.

Hergebruikt ``notify_admins`` zodat de operator (solo + mantelzorg-gebonden) een
storing meteen op Telegram ziet i.p.v. 'm bij toeval te ontdekken. Aangeroepen
door de unattended scripts op de M4:

    docker compose exec -T web python -m app.jobs.notify_ops "<bericht>"

Best-effort: ``notify_admins`` faalt nooit hard. Geen secret in de shell — de
bot-token leeft in de app-config, niet in het aanroepende script.
"""

from __future__ import annotations

import sys

from app.db import SessionLocal
from app.services.notification_service import Notification, notify_admins


def main(message: str) -> None:
    with SessionLocal() as db:
        notify_admins(
            db,
            Notification(
                kind="ops_alert",
                title="⚠️ dewereldvan.ai — ops-melding",
                body=message,
                url="/admin/queue",
                action_label="Open beheer",
            ),
        )
        db.commit()


if __name__ == "__main__":  # pragma: no cover
    main(" ".join(sys.argv[1:]).strip() or "Onbekende storing (geen bericht meegegeven)")
