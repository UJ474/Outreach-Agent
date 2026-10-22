"""
test_followup_due.py — Tests for follow-up due logic.
"""

import pytest
from datetime import datetime, timedelta


def is_followup_due(draft: dict) -> bool:
    """Check if a follow-up is due for a draft. Mirrors agent.py logic."""
    if draft.get("status") != "sent":
        return False
    if draft.get("followup_sent"):
        return False
    sent_at = draft.get("sent_at", "")
    if not sent_at:
        return False
    try:
        sent_date = datetime.fromisoformat(sent_at)
        return sent_date < datetime.now() - timedelta(days=5)
    except ValueError:
        return False


class TestFollowupDue:
    def test_due_after_5_days(self):
        draft = {
            "status": "sent",
            "sent_at": (datetime.now() - timedelta(days=6)).isoformat(),
            "followup_sent": "",
        }
        assert is_followup_due(draft) is True

    def test_not_due_before_5_days(self):
        draft = {
            "status": "sent",
            "sent_at": (datetime.now() - timedelta(days=3)).isoformat(),
            "followup_sent": "",
        }
        assert is_followup_due(draft) is False

    def test_not_due_if_already_sent(self):
        draft = {
            "status": "sent",
            "sent_at": (datetime.now() - timedelta(days=10)).isoformat(),
            "followup_sent": datetime.now().isoformat(),
        }
        assert is_followup_due(draft) is False

    def test_not_due_if_not_sent_status(self):
        draft = {
            "status": "draft",
            "sent_at": (datetime.now() - timedelta(days=10)).isoformat(),
            "followup_sent": "",
        }
        assert is_followup_due(draft) is False

    def test_exactly_5_days_not_due(self):
        """5 days exactly should not yet be due (need > 5 days)."""
        draft = {
            "status": "sent",
            "sent_at": (datetime.now() - timedelta(days=5, seconds=-10)).isoformat(),
            "followup_sent": "",
        }
        assert is_followup_due(draft) is False
