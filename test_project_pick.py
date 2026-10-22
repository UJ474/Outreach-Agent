"""
test_project_pick.py — Tests for project picking logic.
"""

import pytest
from email_writer import pick_projects


PROFILE = {
    "projects": [
        {
            "name": "Newton OOH Agent",
            "url": "https://github.com/UJ474/Newton_OOH_Agent",
            "summary": "multi-agent AI media planning platform",
            "tags": ["agents", "ai", "llm", "automation", "media", "python"]
        },
        {
            "name": "Hawai",
            "url": "https://example.com/hawai",
            "summary": "full-stack airline booking project",
            "tags": ["full-stack", "web", "booking"]
        },
        {
            "name": "Outreach Agent",
            "url": "https://github.com/UJ474/Outreach-Agent",
            "summary": "scrapes sites drafts personalized cold emails with an LLM",
            "tags": ["agents", "scraping", "python", "llm"]
        },
    ]
}


class TestProjectPicking:
    def test_ai_related_picks_agent_project(self):
        facts = {
            "what_they_build": "AI agent evaluation tools",
            "tech_or_domain": ["AI", "agents", "python"],
        }
        lead = {"category": "connect", "goal": "AI agents internship"}

        picked = pick_projects(facts, lead, PROFILE)
        assert len(picked) == 1
        assert picked[0]["name"] in ("Newton OOH Agent", "Outreach Agent")

    def test_web_related_picks_hawai(self):
        facts = {
            "what_they_build": "web booking platform",
            "tech_or_domain": ["web", "full-stack", "booking"],
        }
        lead = {"category": "connect", "goal": "full-stack web development"}

        picked = pick_projects(facts, lead, PROFILE)
        assert len(picked) == 1
        assert picked[0]["name"] == "Hawai"

    def test_openings_picks_two(self):
        facts = {
            "what_they_build": "AI automation tools",
            "tech_or_domain": ["AI", "agents", "python", "llm"],
        }
        lead = {"category": "openings", "goal": "AI agents internship"}

        picked = pick_projects(facts, lead, PROFILE)
        assert len(picked) == 2

    def test_no_overlap_uses_first(self):
        facts = {
            "what_they_build": "quantum computing research",
            "tech_or_domain": ["quantum", "physics"],
        }
        lead = {"category": "connect", "goal": "quantum computing"}

        picked = pick_projects(facts, lead, PROFILE)
        assert len(picked) == 1
        assert picked[0]["name"] == PROFILE["projects"][0]["name"]
