# AI Sales Outreach Agent

An AI-powered sales automation tool that scrapes company websites, writes personalized cold emails using an LLM, and sends them automatically via Gmail — all from a single Python script.

Built by **Utkarsh Jain**, 2nd Year Data Science Student, Newton School of Technology.

---

## What It Does

1. Reads a list of target companies from `leads.csv`
2. Uses **Playwright** to scrape each company's website
3. Feeds the scraped text to **Groq (LLaMA 3.1 8B)** to write a personalized cold email
4. Sends the email automatically via **Gmail SMTP**

---

## Project Structure

```
Sales Outreach Agent/
├── agent.py          # Main loop — ties everything together
├── scraper.py        # Playwright web scraper
├── email_writer.py   # Groq LLM email generator
├── mailer.py         # Gmail SMTP sender
├── leads.csv         # Input file: company name, website, email
├── .env              # API keys and credentials (never commit this)
├── .gitignore
└── requirements.txt
```

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.11+ | Core language |
| Playwright | Headless browser scraping |
| Groq API | LLM inference (LLaMA 3.1 8B Instant) |
| python-dotenv | Load secrets from `.env` |
| Gmail SMTP | Send emails programmatically |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/sales-outreach-agent.git
cd sales-outreach-agent
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install playwright groq python-dotenv
playwright install chromium
```

### 4. Set up your `.env` file

Create a `.env` file in the project root:

```bash
GROQ_API_KEY=your_groq_api_key_here
GMAIL_ADDRESS=yourname@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
```

**Getting your Groq API key:**
- Sign up at [console.groq.com](https://console.groq.com)
- Go to API Keys → Create new key

**Getting your Gmail App Password:**
- Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- Enable 2-Step Verification if not already done
- Create an app password, name it anything (e.g. `outreach agent`)
- Copy the 16-character password into your `.env`

### 5. Add your leads

Edit `leads.csv`:

```csv
company_name,website,email
Notion,https://www.notion.so,founder@notion.so
Linear,https://linear.app,founder@linear.app
```

---

## Usage

```bash
python agent.py
```

The agent will print live progress for each lead:

```
=== AI Sales Outreach Agent ===

Found 2 lead(s) in leads.csv

[1/2] Processing: Notion
  → Scraping https://www.notion.so...
  ✓ Scraped 1423 chars
  → Writing email with Groq...
  ✓ Subject: Helping Notion users do more with AI automation
  → Sending to founder@notion.so...
  ✓ Email sent to founder@notion.so
  Waiting 5s before next email...

[2/2] Processing: Linear
  ...

=== Done ===
```

---

## How Each File Works

### `scraper.py`
Launches a headless Chromium browser using Playwright, navigates to the company website, strips out noise (nav, footer, scripts, styles) by running JavaScript inside the page, and returns up to 1500 characters of clean body text.

Key decisions:
- `headless=True` — browser runs silently in the background
- `wait_until="domcontentloaded"` — fast load, sufficient for text extraction
- `page.evaluate()` — executes JS inside the live browser tab to extract `innerText`
- 1500 char limit — keeps Groq token usage low (free tier: 100k tokens/day)

### `email_writer.py`
Sends the scraped text to Groq's API with a structured prompt that instructs LLaMA 3.1 8B to write a short, personalized cold email. Parses the `SUBJECT:` / `BODY:` response format with a fallback in case the model drifts.

Key decisions:
- `max_tokens=300` — emails should be short; saves daily quota
- `temperature=0.7` — human-sounding without hallucinating
- Strict output format parsing with graceful fallback

### `mailer.py`
Connects to Gmail's SMTP server over SSL (port 465), logs in with your App Password, and sends the email. Returns `True`/`False` so the agent loop can handle failures gracefully.

### `agent.py`
The orchestrator. Reads `leads.csv`, calls `scrape()` → `write_email()` → `send_email()` for each row, with a 5-second delay between sends to avoid Gmail spam filters.

---

## Token Usage (Groq Free Tier)

- Groq free tier: **100,000 tokens/day**
- Each email generation: ~400–600 tokens (prompt + response)
- Scrape limit: 1500 chars ≈ ~375 tokens of input
- Estimated capacity: **~150–200 leads/day** on the free tier

---

## Limitations

- Works best on static or server-rendered websites. Heavy single-page apps (React, Vue) may need `wait_until="networkidle"` in `scraper.py`
- Gmail SMTP has a daily send limit of ~500 emails/day for regular accounts
- LLM output quality depends on how much useful text is on the homepage

---

## Future Improvements

- [ ] Log results (sent / failed / skipped) to a Google Sheet
- [ ] Add a retry mechanism for failed scrapes
- [ ] Support multiple email templates (e.g. different tones per industry)
- [ ] CLI flags: `--dry-run` to preview emails without sending
- [ ] Rate limiting dashboard

---

## License

MIT