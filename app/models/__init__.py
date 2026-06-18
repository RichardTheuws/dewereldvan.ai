"""Model package — single import point for Base, all models, and enums.

Alembic's env.py and the FEATURES layer import everything from here so that
all mappers are registered on a single metadata before use.
"""

from __future__ import annotations

from app.models.ai_chat import AiChatTurn
from app.models.audit import AuditLog
from app.models.base import (
    AuditAction,
    Base,
    IdeaStatus,
    MemberRole,
    MemberStatus,
    ProfileEmphasis,
    ProfileLinkKind,
    RoadmapStatus,
    TimestampMixin,
    Visibility,
)
from app.models.concierge import ConciergeNudgeDismissal
from app.models.feedback import Feedback
from app.models.idea import Idea
from app.models.idea_vote import IdeaVote
from app.models.magic_link import MagicLinkToken
from app.models.member import Member
from app.models.need import Need
from app.models.offering import Offering
from app.models.offering_slug_history import OfferingSlugHistory
from app.models.profile import Profile
from app.models.profile_link import ProfileLink
from app.models.roadmap_item import RoadmapItem
from app.models.tag import Tag, profile_tag

__all__ = [
    "Base",
    "TimestampMixin",
    "MemberStatus",
    "MemberRole",
    "Visibility",
    "AuditAction",
    "ProfileEmphasis",
    "ProfileLinkKind",
    "IdeaStatus",
    "RoadmapStatus",
    "Member",
    "MagicLinkToken",
    "Profile",
    "ProfileLink",
    "Tag",
    "profile_tag",
    "Offering",
    "OfferingSlugHistory",
    "Need",
    "AuditLog",
    "AiChatTurn",
    "ConciergeNudgeDismissal",
    "Feedback",
    "Idea",
    "IdeaVote",
    "RoadmapItem",
]
