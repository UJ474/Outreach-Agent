"""
mailer.py — Sends emails via Gmail SMTP with rate limiting and safety checks.
"""

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

load_dotenv()
logger = logging.getLogger(__name__)

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def _count_sent_today(drafts: list) -> int:
    """Count how many emails were sent today based on drafts.csv data."""
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0
    for row in drafts:
        sent_at = row.get("sent_at", "")
        if sent_at and sent_at.startswith(today):
            count += 1
    return count


def _was_sent_recently(email: str, category: str, drafts: list, days: int = 30) -> bool:
    """Check if the same email+category combo was sent within the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    for row in drafts:
        if (row.get("email", "") == email and
            row.get("status", "") == "sent"):
            sent_at = row.get("sent_at", "")
            if sent_at:
                try:
                    sent_date = datetime.fromisoformat(sent_at)
                    if sent_date > cutoff:
                        return True
                except ValueError:
                    pass
    return False


def send_email(to: str, subject: str, body: str, sender_name: str = "",
               daily_cap: int = 30, all_drafts: list = None,
               category: str = "") -> bool:
    """
    Send a plain-text email via Gmail SMTP.
    Returns True on success, False on failure.
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        logger.error("GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env")
        return False

    if not to or not to.strip():
        logger.error("No recipient email address")
        return False

    # Check daily cap
    if all_drafts is not None:
        sent_today = _count_sent_today(all_drafts)
        if sent_today >= daily_cap:
            logger.warning(f"Daily send cap ({daily_cap}) reached. Skipping.")
            return False

    # Check duplicate sends
    if all_drafts is not None and category:
        if _was_sent_recently(to, category, all_drafts):
            logger.warning(f"Email to {to} for category '{category}' was sent recently. Skipping.")
            return False

    # Build the email
    msg = MIMEMultipart()
    from_header = f"{sender_name} <{GMAIL_ADDRESS}>" if sender_name else GMAIL_ADDRESS
    msg["From"] = from_header
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = GMAIL_ADDRESS
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to, msg.as_string())

        logger.info(f"Email sent to {to}")
        print(f"  ✓ Email sent to {to}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("Auth failed — check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        print("  ✗ Auth failed — check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        return False

    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        print(f"  ✗ SMTP error: {e}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"  ✗ Unexpected error: {e}")
        return False


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_to = GMAIL_ADDRESS
    test_subject = "Test — Outreach Agent"
    test_body = (
        "Hey,\n\n"
        "This is a test email from your Outreach Agent.\n"
        "If you're reading this, Gmail SMTP is working!\n\n"
        "— Utkarsh"
    )
    print(f"Sending test email to {test_to}...")
    send_email(test_to, test_subject, test_body)