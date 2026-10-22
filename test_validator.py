"""
test_validator.py — Tests for the email draft validator.
"""

import pytest
from validator import validate, check_profile


GOOD_PROFILE = {
    "name": "Utkarsh Jain",
    "one_liner": "B.Tech Data Science student",
    "email": "utkarsh@example.com",
    "github": "https://github.com/UJ474",
    "linkedin": "https://linkedin.com/in/utkarsh",
    "portfolio": "",
    "goals": "AI/agents internship",
    "projects": [
        {
            "name": "Newton OOH Agent",
            "url": "https://github.com/UJ474/Newton_OOH_Agent",
            "summary": "Multi-agent AI media planning platform",
            "tags": ["agents", "ai", "llm"]
        }
    ],
    "other_proof": []
}

GOOD_LEAD = {
    "company": "Acme AI",
    "website": "https://acme.ai",
    "person_name": "Jane Roe",
    "person_role": "CTO",
    "email": "jane@acme.ai",
    "category": "openings",
    "goal": "AI agents internship",
    "hook_notes": "Saw their agent-eval launch post",
}

GOOD_FACTS = {
    "what_they_build": "AI evaluation tools for agent pipelines",
    "recent_news": ["Launched agent-eval framework"],
    "tech_or_domain": ["AI", "agents", "evaluation"],
    "open_roles": ["AI Engineer Intern"],
    "hiring_signal": "yes",
    "contribution_ideas": ["Add metrics dashboard"],
    "best_hook": "Their agent-eval framework launch"
}

# A body that passes all checks — exactly constructed
GOOD_BODY = (
    "Hi Jane, I noticed Acme AI recently launched an agent-eval framework for evaluating "
    "agent pipelines, which is a specific challenge I have been working on. "
    "I am Utkarsh Jain, a Data Science student building AI tools. "
    "My project Newton OOH Agent (https://github.com/UJ474/Newton_OOH_Agent) is a "
    "multi-agent AI media planning platform that tackles similar orchestration problems. "
    "I also maintain my work at https://github.com/UJ474 where I explore agent architectures. "
    "I saw your agent-eval launch post and the approach to structured evaluation is compelling. "
    "The AI Engineer Intern role caught my attention given my experience with agent systems. "
    "Would you be open to sharing whether there is an opening on the team?\n\n"
    "Best,\nUtkarsh Jain\nhttps://github.com/UJ474"
)

GOOD_SUBJECT = "Acme agent eval internship interest"


class TestValidatorPasses:
    def test_good_draft_passes(self):
        reasons = validate(GOOD_SUBJECT, GOOD_BODY, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert reasons == [], f"Good draft should pass but got: {reasons}"


class TestValidatorFails:
    def test_too_short_body(self):
        short_body = "Hi Jane, this is short. Best,\nUtkarsh Jain"
        reasons = validate(GOOD_SUBJECT, short_body, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("word count" in r.lower() for r in reasons)

    def test_placeholder_in_body(self):
        body_with_placeholder = GOOD_BODY.replace("agent-eval", "[INSERT PRODUCT]")
        reasons = validate(GOOD_SUBJECT, body_with_placeholder, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("placeholder" in r.lower() for r in reasons)

    def test_banned_phrase(self):
        body_with_banned = GOOD_BODY.replace(
            "I noticed Acme AI",
            "I hope this finds you well and I noticed Acme AI"
        )
        reasons = validate(GOOD_SUBJECT, body_with_banned, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("banned" in r.lower() for r in reasons)

    def test_unknown_url(self):
        body_with_unknown = GOOD_BODY + "\nCheck out https://random-unknown-site.com/page"
        reasons = validate(GOOD_SUBJECT, body_with_unknown, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("unknown url" in r.lower() for r in reasons)

    def test_no_concrete_token(self):
        # Replace all concrete tokens
        generic_body = (
            "Hi Jane, I noticed your company does interesting things in the tech space. "
            "I am Utkarsh Jain, a Data Science student building tools. "
            "My project Newton OOH Agent (https://github.com/UJ474/Newton_OOH_Agent) is a "
            "platform that tackles similar problems. "
            "I also maintain my work at https://github.com/UJ474 where I explore things. "
            "I noticed some interesting work and the approach is compelling. "
            "The role caught my attention given my experience. "
            "Something else here about my background and skills and experience working. "
            "Another sentence about what I find interesting about the industry today. "
            "Would you be open to sharing whether there is a position?\n\n"
            "Best,\nUtkarsh Jain\nhttps://github.com/UJ474"
        )
        # Use empty facts and hook_notes so validator relies on company name
        empty_lead = {**GOOD_LEAD, "hook_notes": "", "company": "XYZCorp123"}
        empty_facts = {
            "what_they_build": None,
            "tech_or_domain": [],
            "best_hook": None,
        }
        reasons = validate(GOOD_SUBJECT, generic_body, GOOD_PROFILE, empty_lead, empty_facts)
        assert any("generic" in r.lower() for r in reasons)

    def test_two_asks(self):
        body_two_asks = GOOD_BODY.replace(
            "Would you be open to sharing whether there is an opening on the team?",
            "Would you be open to sharing? Also could we schedule a call?"
        )
        reasons = validate(GOOD_SUBJECT, body_two_asks, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("question mark" in r.lower() for r in reasons)

    def test_subject_all_caps(self):
        reasons = validate("URGENT Acme AI inquiry now", GOOD_BODY, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("caps" in r.lower() for r in reasons)

    def test_subject_exclamation(self):
        reasons = validate("Acme AI is amazing!", GOOD_BODY, GOOD_PROFILE, GOOD_LEAD, GOOD_FACTS)
        assert any("!" in r for r in reasons)


class TestProfileCheck:
    def test_filled_profile_passes(self):
        missing = check_profile(GOOD_PROFILE)
        assert missing == []

    def test_unfilled_profile_detected(self):
        bad_profile = {**GOOD_PROFILE, "email": "<fill>"}
        missing = check_profile(bad_profile)
        assert len(missing) > 0
        assert "email" in missing[0]
