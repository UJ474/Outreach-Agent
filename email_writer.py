"""
email_writer.py — Fact extraction, project picking, and email drafting using Groq LLM.
Two LLM calls per lead: (1) extract facts, (2) draft email.
"""

import json
import re
import os
import time
import logging
from groq import Groq
from dotenv import load_dotenv
from categories import CATEGORIES

load_dotenv()
logger = logging.getLogger(__name__)

_client = None
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _get_client():
    """Lazy-initialize the Groq client."""
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def _call_groq(messages: list, max_tokens: int = 400, temperature: float = 0.6) -> str:
    """Call Groq with retry on rate-limit/5xx errors."""
    client = _get_client()
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "5" in str(getattr(e, 'status_code', '')):
                delay = 2 ** (attempt + 1)
                logger.warning(f"  Groq error (attempt {attempt+1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Groq API failed after 3 retries")


# ── LLM Call 1: Fact Extraction ──────────────────────────────────────────────

FACT_SYSTEM_PROMPT = """You extract facts from website text. Use ONLY the text provided. If something is not in the text, use null. Do not guess. Return valid JSON only, no markdown."""

FACT_SCHEMA = """{
  "what_they_build": "one sentence",
  "recent_news": ["up to 2 concrete items with the page they came from"],
  "tech_or_domain": ["up to 5 technologies or domains explicitly mentioned"],
  "open_roles": ["role titles found on the careers page, or empty list"],
  "hiring_signal": "yes | no | unknown",
  "contribution_ideas": ["up to 2 concrete, small, plausible ideas grounded in the text, each one sentence"],
  "best_hook": "the single most specific thing worth mentioning in an email, with its source page"
}"""


def extract_facts(scraped_text: dict, lead: dict) -> dict:
    """
    LLM call 1: Extract structured facts from scraped text.
    Returns parsed JSON dict or dict with null values on failure.
    """
    # Combine scraped text, truncate to keep under token budget
    combined = ""
    for url, text in scraped_text.items():
        combined += f"\n--- {url} ---\n{text}\n"
    combined = combined[:6000]  # Stay under ~1500 tokens

    user_prompt = f"""Company: {lead.get('company', '')}
Person: {lead.get('person_name', '')} ({lead.get('person_role', '')})

Website text:
{combined}

Extract facts into this exact JSON schema:
{FACT_SCHEMA}"""

    raw = _call_groq(
        messages=[
            {"role": "system", "content": FACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=500,
        temperature=0.2,
    )

    return _parse_facts_json(raw)


def _parse_facts_json(raw: str) -> dict:
    """Parse JSON from LLM response, handling code fences."""
    # Try direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip code fences and retry
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
    cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("  Could not parse facts JSON, using null defaults")
        return {
            "what_they_build": None,
            "recent_news": [],
            "tech_or_domain": [],
            "open_roles": [],
            "hiring_signal": "unknown",
            "contribution_ideas": [],
            "best_hook": None,
        }


# ── Project Picking (no LLM) ─────────────────────────────────────────────────

def pick_projects(facts: dict, lead: dict, profile: dict) -> list:
    """
    Score profile projects by keyword overlap with facts and lead goal.
    Returns top 1 (or top 2 for 'openings').
    """
    # Build keyword set from facts + goal
    keywords = set()

    for tech in (facts.get("tech_or_domain") or []):
        if tech:
            keywords.add(tech.lower().strip())

    if facts.get("what_they_build"):
        for word in str(facts["what_they_build"]).lower().split():
            if len(word) >= 3:
                keywords.add(word)

    if lead.get("goal"):
        for word in lead["goal"].lower().split():
            if len(word) >= 3:
                keywords.add(word)

    projects = profile.get("projects", [])
    if not projects:
        return []

    # Score each project
    scored = []
    for proj in projects:
        tags = set(t.lower() for t in proj.get("tags", []))
        name_words = set(proj.get("name", "").lower().split())
        summary_words = set(w.lower() for w in proj.get("summary", "").split() if len(w) >= 3)
        all_proj_words = tags | name_words | summary_words
        score = len(keywords & all_proj_words)
        scored.append((score, proj))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Pick top N
    n = 2 if lead.get("category") == "openings" else 1

    # If all scores are 0, use first project
    if scored[0][0] == 0:
        return [projects[0]]

    return [proj for _, proj in scored[:n]]


# ── LLM Call 2: Email Drafting ────────────────────────────────────────────────

COMMON_SYSTEM_PROMPT = """You write short, genuine cold emails from a student to a professional.
Rules:
- 80 to 120 words in the body. Plain text. No bullet points, no markdown, no emojis.
- Exactly one clear ask, placed near the end.
- Open with ONE specific observation about the person's or firm's work taken from FACTS or HOOK_NOTES. Never open with "I hope this finds you well", "I am writing to", or praise without a detail.
- Say who the sender is in one short sentence, then mention at most two projects from PROJECTS with their links.
- Use ONLY information in FACTS, HOOK_NOTES, GOAL, and PROFILE. Do not invent numbers, results, roles, meetings, or relationships.
- Banned words and phrases: passionate, synergy, leverage, cutting-edge, game-changing, "reach out", "pick your brain", "touch base", "opportunity to learn".
- Tone: respectful, direct, curious. Not flattering, not desperate.
Output format exactly:
SUBJECT: <under 8 words, specific, no clickbait>
BODY:
<email body, starting with "Hi <first name>," and ending with "Best,\\n<sender name>" plus one line with GitHub link>"""


def draft_email(facts: dict, lead: dict, profile: dict, chosen_projects: list,
                fix_issues: list = None) -> dict:
    """
    LLM call 2: Draft a personalized email.
    Returns {"subject": str, "body": str}.
    """
    category = lead.get("category", "connect")
    cat_config = CATEGORIES.get(category, CATEGORIES["connect"])

    # Build user prompt
    projects_str = ""
    for p in chosen_projects:
        projects_str += f"- {p['name']}: {p.get('summary', '')} ({p.get('url', '')})\n"

    user_prompt = f"""PROFILE:
Name: {profile.get('name', '')}
One-liner: {profile.get('one_liner', '')}
Goals: {profile.get('goals', '')}
GitHub: {profile.get('github', '')}

PROJECTS:
{projects_str}

LEAD:
Person: {lead.get('person_name', '')}
Role: {lead.get('person_role', '')}
Company: {lead.get('company', '')}
Category: {category}
Goal: {lead.get('goal', '')}
Hook notes: {lead.get('hook_notes', '')}

FACTS:
{json.dumps(facts, indent=2)}

CATEGORY INSTRUCTION: {cat_config['instruction']}
THE ASK: {cat_config['ask']}"""

    # Handle event-specific fields
    if category == "event":
        user_prompt += f"\nEVENT_NAME: {lead.get('event_name', '')}"
        user_prompt += f"\nEVENT_PHASE: {lead.get('event_phase', '')}"

    if fix_issues:
        user_prompt += "\n\nFix these issues:\n" + "\n".join(f"- {r}" for r in fix_issues)

    raw = _call_groq(
        messages=[
            {"role": "system", "content": COMMON_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=400,
        temperature=0.6,
    )

    return _parse_email(raw, lead.get("company", ""))


def draft_followup(original_subject: str, original_body: str, lead: dict,
                   profile: dict, facts: dict) -> dict:
    """Draft a follow-up email (50-70 words)."""
    user_prompt = f"""Write a follow-up to this email that was sent but got no reply.

ORIGINAL SUBJECT: {original_subject}
ORIGINAL BODY:
{original_body}

PROFILE:
Name: {profile.get('name', '')}
GitHub: {profile.get('github', '')}

LEAD:
Person: {lead.get('person_name', '')}
Company: {lead.get('company', '')}
Goal: {lead.get('goal', '')}

Rules for follow-up:
- 50 to 70 words. Plain text.
- Add one new angle: a relevant link, a small new idea, or a one-line clarification.
- Subject must be: Re: {original_subject}
- Start with "Hi {lead.get('person_name', '').split()[0]}," and end with "Best,\\n{profile.get('name', '')}"
- Output format: SUBJECT: ... then BODY: ..."""

    raw = _call_groq(
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=300,
        temperature=0.6,
    )

    return _parse_email(raw, lead.get("company", ""))


def draft_linkedin_note(lead: dict, profile: dict, facts: dict) -> str:
    """Draft a LinkedIn connection message under 280 characters."""
    user_prompt = f"""Write a LinkedIn connection message (under 280 characters) from {profile.get('name', '')} to {lead.get('person_name', '')} at {lead.get('company', '')}.
Goal: {lead.get('goal', '')}
Hook: {lead.get('hook_notes', '')}
About them: {facts.get('what_they_build', '') if facts else ''}

Rules:
- Under 280 characters total
- One specific hook, no generic praise
- No ask bigger than accepting the connection
- Plain text, no emojis
- Return ONLY the message text, nothing else"""

    raw = _call_groq(
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=100,
        temperature=0.6,
    )

    # Ensure under 280 chars
    return raw[:280]


def _parse_email(raw: str, company_name: str) -> dict:
    """Parse the SUBJECT / BODY format from Groq's response."""
    subject = f"Quick note re: {company_name}"
    body = raw

    try:
        lines = raw.splitlines()
        subject_line = next(l for l in lines if l.startswith("SUBJECT:"))
        subject = subject_line.replace("SUBJECT:", "").strip()

        body_start = raw.index("BODY:") + len("BODY:")
        body = raw[body_start:].strip()
    except (StopIteration, ValueError):
        pass

    return {"subject": subject, "body": body}
