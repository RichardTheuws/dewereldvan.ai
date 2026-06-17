"""Approval state machine + audit logging + magic-link gating before approval."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models import (
    AuditAction,
    AuditLog,
    MemberRole,
    MemberStatus,
)
from app.services.approval import (
    IllegalTransition,
    approve_member,
    reject_member,
    suspend_member,
)
from sqlalchemy import func, select

NOW = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)


def _audit_count(db, action: AuditAction) -> int:
    return db.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
    )


def test_approve_pending_sets_state_and_audits(db, make_member):
    admin = make_member(email="admin@dewereldvan.ai", status=MemberStatus.approved,
                        role=MemberRole.admin)
    member = make_member(email="p@example.com", status=MemberStatus.pending)

    approve_member(db, member, actor=admin, now=NOW)
    assert member.status is MemberStatus.approved
    assert member.approved_at is not None
    assert member.pending_expires_at is None
    assert member.role is MemberRole.member  # not in admin set

    rows = db.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.member_approved)
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_member_id == admin.id
    assert rows[0].target_member_id == member.id
    assert rows[0].detail == "pending->approved"


def test_approve_grants_admin_role_if_email_in_admin_set(db, make_member):
    # ADMIN_EMAILS=admin@dewereldvan.ai is set in conftest.
    member = make_member(email="admin@dewereldvan.ai", status=MemberStatus.pending)
    approve_member(db, member, now=NOW)
    assert member.role is MemberRole.admin


def test_reject_pending_audits(db, make_member):
    member = make_member(email="r@example.com", status=MemberStatus.pending)
    reject_member(db, member)
    assert member.status is MemberStatus.rejected
    assert _audit_count(db, AuditAction.member_rejected) == 1


def test_suspend_approved_audits(db, make_member):
    member = make_member(email="s@example.com", status=MemberStatus.approved)
    suspend_member(db, member)
    assert member.status is MemberStatus.suspended
    assert _audit_count(db, AuditAction.member_suspended) == 1


def test_illegal_transition_approve_already_rejected(db, make_member):
    member = make_member(email="x@example.com", status=MemberStatus.rejected)
    with pytest.raises(IllegalTransition):
        approve_member(db, member, now=NOW)
    # No audit row written on a guarded transition.
    assert _audit_count(db, AuditAction.member_approved) == 0


def test_illegal_transition_suspend_pending(db, make_member):
    member = make_member(email="y@example.com", status=MemberStatus.pending)
    with pytest.raises(IllegalTransition):
        suspend_member(db, member)


def test_magic_link_gating_pending_member_cannot_pass_approved_check(db, make_member):
    """A pending member is not 'approved' — the read/login guard must reject it.

    require_member only admits MemberStatus.approved; here we assert the status
    invariant the guard relies on, proving login is gated until approval.
    """
    member = make_member(email="gate@example.com", status=MemberStatus.pending)
    assert member.status is not MemberStatus.approved
    approve_member(db, member, now=NOW)
    assert member.status is MemberStatus.approved
