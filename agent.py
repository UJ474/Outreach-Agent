"""
agent.py — CLI orchestrator for the Outreach Agent.
Reads leads.csv, scrapes, extracts facts, drafts emails, validates, and optionally sends.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

from categories import VALID_CATEGORIES
from email_writer import extract_facts, pick_projects, draft_email, draft_followup, draft_linkedin_note
from mailer import send_email
from scraper import scrape_site
from validator import validate, check_profile

load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────

LEADS_FILE = "leads.csv"
DRAFTS_FILE = "drafts.csv"
NEEDS_MANUAL_FILE = "needs_manual.csv"
PROFILE_FILE = "profile.json"
LOG_FILE = "agent.log"

DAILY_SEND_CAP = int(os.getenv("DAILY_SEND_CAP", "30"))
MIN_DELAY_SEC = int(os.getenv("MIN_DELAY_SEC", "30"))
MAX_DELAY_SEC = int(os.getenv("MAX_DELAY_SEC", "90"))

REQUIRED_LEAD_COLS = ["company", "website", "person_name", "category", "goal"]

DRAFTS_COLUMNS = [
    "id", "created_at", "company", "person_name", "email", "category", "goal",
    "subject", "body", "facts_json", "projects_used", "status", "reject_reasons",
    "sent_at", "followup_sent",
]

MANUAL_COLUMNS = ["company", "person_name", "linkedin", "category", "goal", "note"]

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)
# Quiet down noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_id(lead: dict) -> str:
    """Short hash of (email or linkedin) + category."""
    key = (lead.get("email") or lead.get("linkedin") or lead.get("person_name", ""))
    key += "|" + lead.get("category", "")
    return hashlib.sha256(key.encode()).hexdigest()[:8]


def load_profile() -> dict:
    """Load profile.json."""
    if not os.path.exists(PROFILE_FILE):
        logger.error(f"{PROFILE_FILE} not found. Create it first.")
        sys.exit(1)
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_leads() -> list:
    """Load and validate leads.csv. Returns list of valid lead dicts."""
    if not os.path.exists(LEADS_FILE):
        logger.error(f"{LEADS_FILE} not found.")
        sys.exit(1)

    leads = []
    skipped = 0

    with open(LEADS_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # line 2 = first data row
            # Trim whitespace
            row = {k.strip(): v.strip() if v else "" for k, v in row.items()}

            # Check required columns
            missing = [col for col in REQUIRED_LEAD_COLS if not row.get(col)]
            if missing:
                logger.warning(f"  Row {i}: skipping — missing {', '.join(missing)}")
                skipped += 1
                continue

            # Check valid category
            if row["category"] not in VALID_CATEGORIES:
                logger.warning(f"  Row {i}: skipping — unknown category '{row['category']}'")
                skipped += 1
                continue

            # Event-specific validation
            if row["category"] == "event":
                if not row.get("event_name"):
                    logger.warning(f"  Row {i}: skipping — event category requires event_name")
                    skipped += 1
                    continue
                if row.get("event_phase") not in ("pre", "post_24h", "post_week"):
                    logger.warning(f"  Row {i}: skipping — invalid event_phase")
                    skipped += 1
                    continue

            leads.append(row)

    if skipped:
        logger.info(f"Skipped {skipped} invalid row(s) in {LEADS_FILE}")

    # Dedupe by (email or linkedin) + category
    seen = set()
    deduped = []
    for lead in leads:
        key = (lead.get("email") or lead.get("linkedin") or lead.get("person_name", ""))
        dedup_key = (key, lead["category"])
        if dedup_key in seen:
            logger.info(f"  Skipping duplicate: {lead['person_name']} ({lead['category']})")
            continue
        seen.add(dedup_key)
        deduped.append(lead)

    return deduped


def load_drafts() -> list:
    """Load existing drafts.csv. Returns list of dicts."""
    if not os.path.exists(DRAFTS_FILE):
        return []
    with open(DRAFTS_FILE, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def save_drafts(drafts: list):
    """Write drafts list to drafts.csv (full rewrite via temp file)."""
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8",
                                     dir=".", suffix=".csv", delete=False) as tmp:
        writer = csv.DictWriter(tmp, fieldnames=DRAFTS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in drafts:
            writer.writerow(row)
        tmp_name = tmp.name

    os.replace(tmp_name, DRAFTS_FILE)


def upsert_draft(drafts: list, draft_row: dict) -> list:
    """Insert or update a draft by id."""
    for i, row in enumerate(drafts):
        if row.get("id") == draft_row.get("id"):
            drafts[i] = draft_row
            return drafts
    drafts.append(draft_row)
    return drafts


def save_manual(manual_rows: list):
    """Append to needs_manual.csv."""
    file_exists = os.path.exists(NEEDS_MANUAL_FILE)
    with open(NEEDS_MANUAL_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for row in manual_rows:
            writer.writerow(row)


# ── Main Pipeline ────────────────────────────────────────────────────────────

def process_lead(lead: dict, profile: dict, drafts: list) -> dict | None:
    """
    Process a single lead through the full pipeline.
    Returns the draft row dict, or None if it should go to needs_manual.
    """
    lead_id = make_id(lead)
    person = lead["person_name"]
    company = lead["company"]
    category = lead["category"]

    # Skip if already sent
    for d in drafts:
        if d.get("id") == lead_id and d.get("status") == "sent":
            logger.info(f"  Already sent — skipping")
            return None

    # Check if lead has no email -> needs_manual
    if not lead.get("email"):
        return "needs_manual"

    # Event post_24h without hook_notes -> needs_notes
    if category == "event" and lead.get("event_phase") == "post_24h" and not lead.get("hook_notes"):
        return {
            "id": lead_id,
            "created_at": datetime.now().isoformat(),
            "company": company,
            "person_name": person,
            "email": lead.get("email", ""),
            "category": category,
            "goal": lead.get("goal", ""),
            "subject": "",
            "body": "",
            "facts_json": "",
            "projects_used": "",
            "status": "needs_notes",
            "reject_reasons": "Event post_24h requires hook_notes",
            "sent_at": "",
            "followup_sent": "",
        }

    # Step 1: Scrape
    print(f"  scraping...")
    scraped = scrape_site(lead["website"], lead.get("extra_urls", ""))
    total_chars = sum(len(t) for t in scraped.values())
    print(f"  scraped {len(scraped)} pages ({total_chars:,} chars)")

    if not scraped:
        logger.warning(f"  No pages scraped for {company}")

    # Step 2: Extract facts
    print(f"  extracting facts...")
    facts = extract_facts(scraped, lead)
    facts_ok = facts.get("what_they_build") is not None
    print(f"  facts {'ok' if facts_ok else 'partial'}")

    # Step 3: Pick projects
    chosen = pick_projects(facts, lead, profile)
    proj_names = ", ".join(p["name"] for p in chosen)
    print(f"  projects: {proj_names}")

    # Step 4: Draft email
    print(f"  drafting...")
    email = draft_email(facts, lead, profile, chosen)

    # Step 5: Validate
    reasons = validate(email["subject"], email["body"], profile, lead, facts)

    # Retry once if validation fails
    if reasons:
        logger.info(f"  Draft failed validation: {reasons}. Retrying...")
        email = draft_email(facts, lead, profile, chosen, fix_issues=reasons)
        reasons = validate(email["subject"], email["body"], profile, lead, facts)

    status = "rejected" if reasons else "draft"
    word_count = len(email["body"].split())
    print(f"  draft {'rejected' if reasons else 'ok'} ({word_count} words) -> id {lead_id}")

    if reasons:
        logger.info(f"  Reject reasons: {reasons}")

    draft_row = {
        "id": lead_id,
        "created_at": datetime.now().isoformat(),
        "company": company,
        "person_name": person,
        "email": lead.get("email", ""),
        "category": category,
        "goal": lead.get("goal", ""),
        "subject": email["subject"],
        "body": email["body"],
        "facts_json": json.dumps(facts),
        "projects_used": proj_names,
        "status": status,
        "reject_reasons": "; ".join(reasons) if reasons else "",
        "sent_at": "",
        "followup_sent": "",
    }

    return draft_row


# ── CLI Commands ─────────────────────────────────────────────────────────────

def cmd_dry_run(args, profile: dict):
    """Default mode: generate drafts without sending."""
    leads = load_leads()
    drafts = load_drafts()
    manual_rows = []

    if args.category:
        leads = [l for l in leads if l["category"] == args.category]

    if args.limit:
        leads = leads[:args.limit]

    print(f"\n=== Outreach Agent — Dry Run ({len(leads)} leads) ===\n")

    for i, lead in enumerate(leads, start=1):
        print(f"[{i}/{len(leads)}] {lead['person_name']} @ {lead['company']} ({lead['category']})")

        try:
            result = process_lead(lead, profile, drafts)

            if result == "needs_manual":
                # Generate LinkedIn note and save to manual list
                print(f"  no email — generating LinkedIn note...")
                scraped = scrape_site(lead["website"], lead.get("extra_urls", ""))
                facts = extract_facts(scraped, lead) if scraped else {}
                note = draft_linkedin_note(lead, profile, facts)
                manual_rows.append({
                    "company": lead["company"],
                    "person_name": lead["person_name"],
                    "linkedin": lead.get("linkedin", ""),
                    "category": lead["category"],
                    "goal": lead.get("goal", ""),
                    "note": note,
                })
                print(f"  -> needs_manual.csv")
            elif result is not None:
                drafts = upsert_draft(drafts, result)
        except Exception as e:
            logger.error(f"  Error processing {lead['person_name']}: {e}")
            print(f"  ✗ Error: {e}")

        print()

    save_drafts(drafts)
    if manual_rows:
        save_manual(manual_rows)

    # Summary
    statuses = {}
    for d in drafts:
        s = d.get("status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1

    print("=== Summary ===")
    for s, c in sorted(statuses.items()):
        print(f"  {s}: {c}")
    if manual_rows:
        print(f"  needs_manual: {len(manual_rows)}")
    print(f"\nDrafts saved to {DRAFTS_FILE}")


def cmd_send(profile: dict):
    """Send all approved drafts."""
    drafts = load_drafts()
    approved = [d for d in drafts if d.get("status") == "approved" and d.get("email")]

    if not approved:
        print("No approved drafts to send.")
        return

    print(f"\n=== Sending {len(approved)} approved draft(s) ===\n")

    sent_count = 0
    for i, draft in enumerate(approved, start=1):
        print(f"[{i}/{len(approved)}] {draft['person_name']} @ {draft['company']}")

        success = send_email(
            to=draft["email"],
            subject=draft["subject"],
            body=draft["body"],
            sender_name=profile.get("name", ""),
            daily_cap=DAILY_SEND_CAP,
            all_drafts=drafts,
            category=draft.get("category", ""),
        )

        if success:
            draft["status"] = "sent"
            draft["sent_at"] = datetime.now().isoformat()
            sent_count += 1
        else:
            draft["status"] = "failed"

        # Random delay between sends
        if i < len(approved):
            delay = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
            print(f"  Waiting {delay:.0f}s...")
            time.sleep(delay)

    save_drafts(drafts)
    print(f"\n=== Sent {sent_count}/{len(approved)} emails ===")


def cmd_approve(ids: list):
    """Mark specific drafts as approved."""
    drafts = load_drafts()
    approved = 0

    for draft in drafts:
        if draft.get("id") in ids and draft.get("status") == "draft":
            draft["status"] = "approved"
            approved += 1

    save_drafts(drafts)
    print(f"Approved {approved} draft(s).")


def cmd_approve_all():
    """Mark all valid drafts as approved (with confirmation)."""
    drafts = load_drafts()
    eligible = [d for d in drafts if d.get("status") == "draft"]

    if not eligible:
        print("No drafts eligible for approval.")
        return

    print(f"\n{len(eligible)} draft(s) eligible for approval:")
    for d in eligible:
        print(f"  {d['id']} — {d['person_name']} @ {d['company']} ({d['category']})")

    confirm = input("\nApprove all? (y/N): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    for d in drafts:
        if d.get("status") == "draft":
            d["status"] = "approved"

    save_drafts(drafts)
    print(f"Approved {len(eligible)} draft(s).")


def cmd_show():
    """Print a table of all drafts."""
    drafts = load_drafts()

    if not drafts:
        print("No drafts found.")
        return

    print(f"\n{'ID':<10} {'Person':<20} {'Company':<20} {'Category':<12} {'Status':<12}")
    print("-" * 74)
    for d in drafts:
        print(f"{d.get('id', ''):<10} {d.get('person_name', ''):<20} "
              f"{d.get('company', ''):<20} {d.get('category', ''):<12} "
              f"{d.get('status', ''):<12}")


def cmd_followups(args, profile: dict):
    """Generate follow-up emails for sent drafts that are 5+ days old."""
    drafts = load_drafts()
    cutoff = datetime.now() - timedelta(days=5)

    due = []
    for d in drafts:
        if d.get("status") == "sent" and not d.get("followup_sent"):
            sent_at = d.get("sent_at", "")
            if sent_at:
                try:
                    sent_date = datetime.fromisoformat(sent_at)
                    if sent_date < cutoff:
                        due.append(d)
                except ValueError:
                    pass

    if not due:
        print("No follow-ups due.")
        return

    print(f"\n=== Follow-ups due: {len(due)} ===\n")

    for i, d in enumerate(due, start=1):
        print(f"[{i}/{len(due)}] {d['person_name']} @ {d['company']}")

        try:
            lead = {
                "person_name": d["person_name"],
                "company": d["company"],
                "category": d["category"],
                "goal": d["goal"],
                "email": d["email"],
            }

            facts = {}
            try:
                facts = json.loads(d.get("facts_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass

            followup = draft_followup(d["subject"], d["body"], lead, profile, facts)

            # Validate follow-up
            reasons = validate(followup["subject"], followup["body"], profile, lead, facts,
                              is_followup=True)

            if reasons:
                print(f"  Follow-up validation failed: {reasons}")
                continue

            word_count = len(followup["body"].split())
            print(f"  follow-up drafted ({word_count} words)")

            if args.send:
                success = send_email(
                    to=d["email"],
                    subject=followup["subject"],
                    body=followup["body"],
                    sender_name=profile.get("name", ""),
                    daily_cap=DAILY_SEND_CAP,
                    all_drafts=drafts,
                )
                if success:
                    d["followup_sent"] = datetime.now().isoformat()
                    print(f"  ✓ Follow-up sent")
            else:
                print(f"  Subject: {followup['subject']}")
                print(f"  (dry-run — use --send to send)")

        except Exception as e:
            logger.error(f"  Follow-up error for {d['person_name']}: {e}")
            print(f"  ✗ Error: {e}")

        print()

    save_drafts(drafts)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Outreach Agent — Personal email outreach tool")
    parser.add_argument("--send", action="store_true", help="Send approved drafts")
    parser.add_argument("--approve", nargs="+", metavar="ID", help="Approve drafts by ID")
    parser.add_argument("--approve-all", action="store_true", help="Approve all valid drafts")
    parser.add_argument("--category", type=str, help="Only process this category")
    parser.add_argument("--limit", type=int, help="Process at most N leads")
    parser.add_argument("--followups", action="store_true", help="Generate/send follow-ups")
    parser.add_argument("--show", action="store_true", help="Show all drafts")

    args = parser.parse_args()

    # Load profile
    profile = load_profile()

    # Profile check
    missing_fields = check_profile(profile)
    if missing_fields:
        if args.send:
            print(f"ERROR: profile.json has unfilled fields: {', '.join(missing_fields)}")
            print("Fill them before sending. Aborting.")
            sys.exit(1)
        else:
            print(f"WARNING: profile.json has unfilled fields: {', '.join(missing_fields)}")
            print("Fill them before sending.\n")

    # Route commands
    if args.show:
        cmd_show()
    elif args.approve:
        cmd_approve(args.approve)
    elif args.approve_all:
        cmd_approve_all()
    elif args.followups:
        cmd_followups(args, profile)
    elif args.send:
        cmd_send(profile)
    else:
        cmd_dry_run(args, profile)


if __name__ == "__main__":
    main()