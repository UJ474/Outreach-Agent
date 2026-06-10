"""
agent.py — Ties everything together.
Reads leads.csv, scrapes each website, writes a personalized email, and sends it.
"""

import csv
import time
from scraper import scrape
from email_writer import write_email
from mailer import send_email

LEADS_FILE = "leads.csv"
DELAY_BETWEEN_EMAILS = 5  # seconds — avoids triggering Gmail spam filters


def run():
    print("=== AI Sales Outreach Agent ===\n")

    with open(LEADS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        leads = list(reader)

    print(f"Found {len(leads)} lead(s) in {LEADS_FILE}\n")

    for i, lead in enumerate(leads, start=1):
        company = lead["company_name"].strip()
        website = lead["website"].strip()
        recipient = lead["email"].strip()

        print(f"[{i}/{len(leads)}] Processing: {company}")

        # Step 1 — Scrape
        print(f"  → Scraping {website}...")
        text = scrape(website)
        if text.startswith("ERROR"):
            print(f"  ✗ Skipping — {text}\n")
            continue
        print(f"  ✓ Scraped {len(text)} chars")

        # Step 2 — Write email
        print(f"  → Writing email with Groq...")
        email = write_email(company, text)
        print(f"  ✓ Subject: {email['subject']}")

        # Step 3 — Send
        print(f"  → Sending to {recipient}...")
        success = send_email(recipient, email["subject"], email["body"])

        if success and i < len(leads):
            print(f"  Waiting {DELAY_BETWEEN_EMAILS}s before next email...\n")
            time.sleep(DELAY_BETWEEN_EMAILS)

    print("\n=== Done ===")


if __name__ == "__main__":
    run()