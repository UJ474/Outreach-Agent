"""
email_writer.py — Uses Groq (llama-3.1-8b-instant) to write a
personalized cold email based on scraped company website text.
"""

from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def write_email(company_name: str, scraped_text: str) -> dict:
    """
    Given a company name and scraped website text, returns a dict:
      { "subject": "...", "body": "..." }
    """

    prompt = f"""You are Utkarsh Jain, a 2nd year Data Science student at Newton School of Technology.
You are reaching out to companies to offer your skills in AI automation, data pipelines, and Python development.

Here is what you know about {company_name} from their website:
\"\"\"
{scraped_text}
\"\"\"

Write a short, personalized cold email to someone at {company_name}.
- Subject line: specific to what they do, not generic
- Body: 3–4 sentences max. Mention ONE specific thing from their website.
- End with a simple CTA (e.g. "Would you be open to a quick 15-min chat?")
- Tone: confident, friendly, not salesy
- Sign off as: Utkarsh Jain

Respond ONLY in this exact format, nothing else:
SUBJECT: <subject line here>
BODY:
<email body here>
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,      # emails should be short
        temperature=0.7,
    )

    raw = response.choices[0].message.content.strip()
    return _parse_email(raw, company_name)


def _parse_email(raw: str, company_name: str) -> dict:
    """Parses the SUBJECT / BODY format from Groq's response."""
    subject = f"Quick note re: {company_name}"  # fallback
    body = raw                                   # fallback: use full text

    try:
        lines = raw.splitlines()
        subject_line = next(l for l in lines if l.startswith("SUBJECT:"))
        subject = subject_line.replace("SUBJECT:", "").strip()

        body_start = raw.index("BODY:") + len("BODY:")
        body = raw[body_start:].strip()
    except (StopIteration, ValueError):
        pass  # fallback values already set

    return {"subject": subject, "body": body}


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_text = (
        "Notion is a connected workspace where better, faster work happens. "
        "Teams use Notion to write docs, manage projects, and organize knowledge — all in one place. "
        "Notion AI helps you summarize, translate, and generate content instantly."
    )

    result = write_email("Notion", sample_text)
    print("SUBJECT:", result["subject"])
    print()
    print("BODY:")
    print(result["body"])
