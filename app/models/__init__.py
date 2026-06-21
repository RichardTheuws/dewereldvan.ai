"""Model package — single import point for Base, all models, and enums.

Alembic's env.py and the FEATURES layer import everything from here so that
all mappers are registered on a single metadata before use.
"""

from __future__ import annotations

from app.models.ai_chat import AiChatTurn
from app.models.ai_spend_log import AiSpendLog
from app.models.audit import AuditLog
from app.models.base import (
    AuditAction,
    Base,
    ConnectionStatus,
    EventFrequency,
    IdeaStatus,
    MatchStatus,
    MemberRole,
    MemberStatus,
    NewsRole,
    PostKind,
    PostReviewState,
    PostSourceKind,
    ProfileEmphasis,
    ProfileLinkKind,
    RoadmapStatus,
    TimestampMixin,
    Visibility,
)
from app.models.concierge import ConciergeNudgeDismissal, ConciergeTurn
from app.models.connection import Connection
from app.models.discovery_run import DiscoveryRun
from app.models.feedback import Feedback
from app.models.group_invite import GroupInvite
from app.models.idea import Idea
from app.models.idea_vote import IdeaVote
from app.models.magic_link import MagicLinkToken
from app.models.match_suggestion import MatchSuggestion
from app.models.member import Member
from app.models.member_channel import MemberChannel
from app.models.notification_pref import NotificationPref
from app.models.need import Need
from app.models.offering import Offering
from app.models.offering_slug_history import OfferingSlugHistory
from app.models.personal_token import PersonalToken
from app.models.post import Post
from app.models.profile import Profile
from app.models.profile_link import ProfileLink
from app.models.roadmap_item import RoadmapItem
from app.models.tag import Tag, profile_tag
from app.models.tool import Tool, profile_tool

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
    "PostKind",
    "PostReviewState",
    "PostSourceKind",
    "EventFrequency",
    "NewsRole",
    "MatchStatus",
    "ConnectionStatus",
    "Member",
    "MagicLinkToken",
    "Profile",
    "ProfileLink",
    "Tag",
    "profile_tag",
    "Tool",
    "profile_tool",
    "Offering",
    "OfferingSlugHistory",
    "Need",
    "AuditLog",
    "AiChatTurn",
    "AiSpendLog",
    "ConciergeNudgeDismissal",
    "ConciergeTurn",
    "Feedback",
    "GroupInvite",
    "Idea",
    "IdeaVote",
    "RoadmapItem",
    "Post",
    "MatchSuggestion",
    "Connection",
    "PersonalToken",
    "DiscoveryRun",
    "MemberChannel",
    "NotificationPref",
]
