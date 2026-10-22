"""
categories.py — Per-category prompt instructions for email drafting.
"""

CATEGORIES = {
    "openings": {
        "instruction": (
            "State the kind of role sought (from GOAL). Connect the best hook about their "
            "product to one relevant project. If FACTS lists open_roles, mention the most "
            "relevant one by title; if none, say the sender is interested in internship-level "
            "work in that area without claiming a posted role."
        ),
        "ask": "whether there is an opening, or who the right person to speak with is.",
    },
    "contribute": {
        "instruction": (
            "Name something specific they are building. Offer ONE concrete contribution "
            "taken from contribution_ideas or hook_notes (a small feature, fix, prototype, "
            "or analysis). Say it is small and can start without commitment. Link the most "
            "relevant project as proof."
        ),
        "ask": "whether a small task, issue, or demo from the sender would be useful.",
    },
    "connect": {
        "instruction": (
            "Show understanding of what the firm builds in one sentence. Share one short "
            "observation or idea. Keep it light, no job ask."
        ),
        "ask": "a 15-minute call, or their thoughts on one specific question.",
    },
    "advice": {
        "instruction": (
            "Ask exactly one specific question tied to the person's own work or path. "
            "Mention the sender's goal in one line so the question has context."
        ),
        "ask": "a short reply with their view; explicitly no call needed.",
    },
    "opensource": {
        "instruction": (
            "Refer to the repo or issue in extra_urls/hook_notes. Say what the sender "
            "studied and what they plan to change. Do not claim any work already done "
            "unless it is in PROFILE."
        ),
        "ask": "whether the approach is welcome before the sender opens a PR.",
    },
    "event": {
        "instruction": (
            "Use EVENT_NAME and EVENT_PHASE. "
            "pre: say the sender is looking forward to their session and ask one question. "
            "post_24h: name one specific takeaway from HOOK_NOTES and what the sender will "
            "try because of it, thank them. "
            "post_week: share one thing the sender built or wrote after the event (only if "
            "in PROFILE or HOOK_NOTES)."
        ),
        "ask": (
            "one specific question, feedback, or staying in touch. If HOOK_NOTES is empty "
            "for post_24h, mark the lead needs_notes and skip drafting."
        ),
    },
}

VALID_CATEGORIES = set(CATEGORIES.keys())
