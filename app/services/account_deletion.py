"""Account-verwijdering (AVG) — wis een lid + ALLES wat eraan hangt.

Mandaat (eigenaar, "hoogst zorgvuldig"): na ``delete_member_completely`` bestaat
er GEEN enkele rij meer met dit ``member_id`` in welke tabel dan ook — behalve één
geanonimiseerde, PII-loze audit-rij van de wissing zelf — en het foto-bestand op
schijf is weg.

Waarom EXPLICIET verwijderen i.p.v. op DB-cascade leunen
--------------------------------------------------------
De meeste FK's naar ``member.id`` zijn ``ON DELETE CASCADE`` (profile → offering/
need/profile_link/profile_tag/offering_slug_history, magic_link_token, feedback,
idea → idea_vote, idea_vote, concierge_nudge_dismissal, ai_chat_turn). Maar:

- SQLite (de test-DB) handhaaft FK-cascades alleen met ``PRAGMA foreign_keys=ON``
  per connectie; de suite zet die pragma NIET. Op cascade leunen zou betekenen dat
  de compleetheid niet test-bewijsbaar is — en stilzwijgend wees-data kan
  achterlaten als de productie-config ooit afwijkt.
- ``audit_log`` (actor + target) en ``group_invite.created_by`` zijn ``SET NULL``;
  die rijen blijven per ontwerp bestaan, dus we moeten de verwijzingen expliciet
  nullen zodat er geen PII-anker naar het gewiste lid achterblijft.

Daarom verwijdert deze service elke afhankelijke rij expliciet, in FK-veilige
volgorde (kinderen vóór ouders), en nult daarna de SET-NULL-verwijzingen. Dat is
robuust ongeacht of de onderliggende engine cascades handhaaft.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    AiChatTurn,
    AuditAction,
    AuditLog,
    ConciergeNudgeDismissal,
    Feedback,
    GroupInvite,
    Idea,
    IdeaVote,
    MagicLinkToken,
    Member,
    Need,
    Offering,
    OfferingSlugHistory,
    Profile,
    ProfileLink,
    profile_tag,
)
from app.services.photo_service import delete_photo


def delete_member_completely(db: Session, member: Member) -> None:
    """Wis ``member`` en ALLE bijbehorende data definitief (AVG, onomkeerbaar).

    Volgorde:
    1. Foto-bestand op schijf opruimen (idempotent; faalt niet als het al weg is).
    2. Eén PII-loze audit-rij van de wissing zelf schrijven (actor/target = NULL).
    3. Bestaande audit-/invite-verwijzingen naar dit lid nullen (SET NULL-FK's),
       zodat de delete niet blokkeert en geen PII-anker achterblijft.
    4. Alle afhankelijke rijen verwijderen (kinderen vóór ouders).
    5. De member-row zelf verwijderen.

    Na afloop is er geen rij meer met dit ``member_id`` in welke tabel dan ook,
    behalve de geanonimiseerde ``member_deleted``-audit-rij. De caller commit.
    """
    member_id = member.id

    # --- 1. Foto-bestand op schijf (vóór we de profile-row kwijt zijn) --------
    profile_ids = list(
        db.scalars(select(Profile.id).where(Profile.member_id == member_id))
    )
    for photo_url in db.scalars(
        select(Profile.photo_url).where(Profile.member_id == member_id)
    ):
        delete_photo(photo_url)  # idempotent: None/onbekend = no-op

    # --- 2. PII-loze audit-rij van de wissing zelf ----------------------------
    # actor/target bewust NULL: geen e-mail, geen naam, geen member_id — alleen
    # het feit dát er een zelf-wissing plaatsvond (minimale grondslag-traceability).
    db.add(
        AuditLog(
            action=AuditAction.member_deleted,
            actor_member_id=None,
            target_member_id=None,
            detail="member_self_deleted",
        )
    )

    # --- 3. SET-NULL-verwijzingen expliciet nullen ----------------------------
    # Deze rijen blijven per ontwerp bestaan (admin-spoor / invite-historie), maar
    # mogen geen anker naar het gewiste lid houden. Expliciet i.p.v. op DB-cascade
    # leunen (SQLite handhaaft SET NULL niet zonder pragma).
    db.execute(
        update(AuditLog)
        .where(AuditLog.actor_member_id == member_id)
        .values(actor_member_id=None)
    )
    db.execute(
        update(AuditLog)
        .where(AuditLog.target_member_id == member_id)
        .values(target_member_id=None)
    )
    db.execute(
        update(GroupInvite)
        .where(GroupInvite.created_by == member_id)
        .values(created_by=None)
    )

    # --- 4. Afhankelijke rijen verwijderen (kinderen vóór ouders) -------------
    if profile_ids:
        # offering_slug_history hangt aan offering (offering_id), dus eerst weg.
        offering_ids = list(
            db.scalars(
                select(Offering.id).where(Offering.profile_id.in_(profile_ids))
            )
        )
        if offering_ids:
            db.execute(
                delete(OfferingSlugHistory).where(
                    OfferingSlugHistory.offering_id.in_(offering_ids)
                )
            )
        db.execute(delete(Offering).where(Offering.profile_id.in_(profile_ids)))
        db.execute(delete(Need).where(Need.profile_id.in_(profile_ids)))
        db.execute(
            delete(ProfileLink).where(ProfileLink.profile_id.in_(profile_ids))
        )
        # M2M-associaties wissen — NIET de gedeelde ``tag``-rijen zelf (die horen
        # bij andere leden). We raken alleen de koppelrijen van dit profiel.
        db.execute(
            delete(profile_tag).where(profile_tag.c.profile_id.in_(profile_ids))
        )

    # idea → idea_vote: eerst alle stemmen die bij de ideeën van dit lid horen,
    # dan de stemmen die dit lid zelf op andermans ideeën uitbracht, dan de ideeën.
    idea_ids = list(
        db.scalars(select(Idea.id).where(Idea.member_id == member_id))
    )
    if idea_ids:
        db.execute(delete(IdeaVote).where(IdeaVote.idea_id.in_(idea_ids)))
    db.execute(delete(IdeaVote).where(IdeaVote.member_id == member_id))
    db.execute(delete(Idea).where(Idea.member_id == member_id))

    db.execute(delete(Feedback).where(Feedback.member_id == member_id))
    db.execute(
        delete(ConciergeNudgeDismissal).where(
            ConciergeNudgeDismissal.member_id == member_id
        )
    )
    db.execute(delete(AiChatTurn).where(AiChatTurn.member_id == member_id))
    db.execute(delete(MagicLinkToken).where(MagicLinkToken.member_id == member_id))
    db.execute(delete(Profile).where(Profile.member_id == member_id))

    # --- 5. De member-row zelf ------------------------------------------------
    db.execute(delete(Member).where(Member.id == member_id))
    db.flush()
