"""
mailer.py — Sends emails via Gmail SMTP.
Uses an App Password (not your real Gmail password).
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv()

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


def send_email(to: str, subject: str, body: str) -> bool:
    """
    Sends an email via Gmail SMTP.
    Returns True on success, False on failure.
    """

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("ERROR: GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env")
        return False

    # Build the email
    msg = MIMEMultipart()
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to, msg.as_string())

        print(f"  ✓ Email sent to {to}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("  ✗ Auth failed — check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        return False

    except smtplib.SMTPException as e:
        print(f"  ✗ SMTP error: {e}")
        return False

    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        return False


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Sends a test email to yourself
    test_to = GMAIL_ADDRESS  # sends to yourself as a sanity check
    test_subject = "Test — Sales Outreach Agent"
    test_body = (
        "Hey,\n\n"
        "This is a test email from your AI Sales Outreach Agent.\n"
        "If you're reading this, Gmail SMTP is working!\n\n"
        "— Utkarsh"
    )

    print(f"Sending test email to {test_to}...")
    send_email(test_to, test_subject, test_body)