"""
validator.py — Programmatic checks on email drafts.
Returns a list of failure reasons (empty = pass).
"""

import json
import re


BANNED_PHRASES = [
    "passionate", "synergy", "leverage", "cutting-edge", "game-changing",
    "reach out", "pick your brain", "touch base", "opportunity to learn",
    "i hope this finds you well", "i am writing to",
]


def validate(subject: str, body: str, profile: dict, lead: dict,
             facts: dict = None, is_followup: bool = False) -> list:
    """
    Validate a draft email. Returns list of failure reason strings.
    Empty list means the draft passes.
    """
    reasons = []

    # 1. Body word count
    words = body.split()
    word_count = len(words)
    if is_followup:
        if word_count < 40 or word_count > 90:
            reasons.append(f"Follow-up body word count {word_count} not in 40-90 range")
    else:
        if word_count < 70 or word_count > 140:
            reasons.append(f"Body word count {word_count} not in 70-140 range")

    # 2. Subject checks
    if not subject or not subject.strip():
        reasons.append("Subject is empty")
    else:
        subj_words = subject.strip().split()
        if len(subj_words) < 3 or len(subj_words) > 9:
            reasons.append(f"Subject word count {len(subj_words)} not in 3-9 range")
        if any(w == w.upper() and len(w) > 2 and w.isalpha() for w in subj_words):
            reasons.append("Subject contains ALL CAPS word(s)")
        if "!" in subject:
            reasons.append("Subject contains '!'")

    # 3. No unfilled placeholders
    placeholder_patterns = ["[", "]", "<", ">", "{", "}", "TODO", "<fill>"]
    for pat in placeholder_patterns:
        if pat in body:
            reasons.append(f"Body contains placeholder: '{pat}'")
            break
    for pat in placeholder_patterns:
        if pat in subject:
            reasons.append(f"Subject contains placeholder: '{pat}'")
            break

    # 4. Starts with Hi <first name>,
    first_name = lead.get("person_name", "").strip().split()[0] if lead.get("person_name", "").strip() else ""
    if first_name:
        expected_start = f"Hi {first_name},"
        if not body.strip().startswith(expected_start):
            reasons.append(f"Body should start with '{expected_start}'")

    # 5. No banned phrases
    body_lower = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase in body_lower:
            reasons.append(f"Body contains banned phrase: '{phrase}'")

    # 6. Link checks
    # Find all URLs in body
    url_pattern = re.compile(r'https?://[^\s,)]+')
    body_urls = url_pattern.findall(body)

    # Build allowed URLs from profile
    profile_urls = set()
    if profile.get("github"):
        profile_urls.add(profile["github"].rstrip("/"))
    if profile.get("linkedin"):
        profile_urls.add(profile["linkedin"].rstrip("/"))
    if profile.get("portfolio"):
        profile_urls.add(profile["portfolio"].rstrip("/"))
    for proj in profile.get("projects", []):
        if proj.get("url"):
            profile_urls.add(proj["url"].rstrip("/"))

    # Build allowed external URLs
    allowed_external = set()
    if lead.get("website"):
        allowed_external.add(lead["website"].rstrip("/"))
    if lead.get("extra_urls"):
        for u in lead["extra_urls"].split(";"):
            u = u.strip()
            if u:
                allowed_external.add(u.rstrip("/"))

    # Check: at least one profile link present
    has_profile_link = any(
        any(pu in bu for pu in profile_urls)
        for bu in body_urls
    )
    if not has_profile_link and not is_followup:
        reasons.append("Body must contain at least one link from profile.json")

    # Check: no unknown URLs
    for bu in body_urls:
        bu_clean = bu.rstrip("/")
        is_allowed = False
        for pu in profile_urls:
            if pu in bu_clean or bu_clean in pu:
                is_allowed = True
                break
        if not is_allowed:
            for eu in allowed_external:
                if eu in bu_clean or bu_clean in eu:
                    is_allowed = True
                    break
        if not is_allowed:
            # Check if it's a subdomain/subpath of the lead website
            website = lead.get("website", "").rstrip("/")
            if website and bu_clean.startswith(website):
                is_allowed = True
        if not is_allowed:
            reasons.append(f"Body contains unknown URL: {bu}")

    # 7. Contains at least one concrete token from FACTS or HOOK_NOTES
    concrete_tokens = set()
    if lead.get("hook_notes"):
        # Extract significant words (3+ chars) from hook_notes
        for word in lead["hook_notes"].split():
            cleaned = re.sub(r'[^\w]', '', word)
            if len(cleaned) >= 4:
                concrete_tokens.add(cleaned.lower())

    if facts:
        # Add company/product references from facts
        if facts.get("what_they_build"):
            for word in str(facts["what_they_build"]).split():
                cleaned = re.sub(r'[^\w]', '', word)
                if len(cleaned) >= 4:
                    concrete_tokens.add(cleaned.lower())
        if facts.get("tech_or_domain"):
            for tech in facts["tech_or_domain"]:
                if tech:
                    concrete_tokens.add(tech.lower().strip())
        if facts.get("best_hook"):
            for word in str(facts["best_hook"]).split():
                cleaned = re.sub(r'[^\w]', '', word)
                if len(cleaned) >= 4:
                    concrete_tokens.add(cleaned.lower())

    # Also add company name as a concrete token
    company = lead.get("company", "").strip()
    if company:
        concrete_tokens.add(company.lower())

    if concrete_tokens and not is_followup:
        body_lower_words = set(re.sub(r'[^\w\s]', '', body.lower()).split())
        found = any(token in body_lower_words or token in body.lower() for token in concrete_tokens)
        if not found:
            reasons.append("Too generic — body doesn't reference any concrete fact about the company")

    # 8. Exactly one question mark in last 3 sentences
    sentences = re.split(r'(?<=[.!?])\s+', body.strip())
    last_three = sentences[-3:] if len(sentences) >= 3 else sentences
    last_three_text = " ".join(last_three)
    q_count = last_three_text.count("?")
    if q_count != 1:
        reasons.append(f"Expected exactly 1 question mark in last 3 sentences, found {q_count}")

    # 9. Sender name in sign-off
    sender_name = profile.get("name", "")
    if sender_name and sender_name not in body:
        reasons.append(f"Sender name '{sender_name}' not found in sign-off")

    return reasons


def check_profile(profile: dict) -> list:
    """
    Check profile.json for unfilled <fill> fields.
    Returns list of field paths that still contain <fill>.
    """
    missing = []

    def _check(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _check(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _check(v, f"{path}[{i}]")
        elif isinstance(obj, str):
            if "<fill" in obj.lower():
                missing.append(path)

    _check(profile)
    return missing
