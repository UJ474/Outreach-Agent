# Outreach Agent

A personal outreach tool that scrapes company websites, extracts facts with an LLM, and drafts specific, honest cold emails for reaching people at specific firms.

**Not a mass mailer.** Every email is tailored to the person and company using scraped data. Dry-run is the default — nothing sends unless you explicitly approve and use `--send`.

## What it does

Six outreach categories, each with its own prompt and ask:

| Category | Purpose |
|---|---|
| `openings` | Ask about internships/jobs, connect your projects to their work |
| `contribute` | Offer a small, concrete contribution to something they're building |
| `connect` | Light intro, share an observation, ask for a short call |
| `advice` | Ask one specific question tied to their work or path |
| `opensource` | Propose a PR or contribution to their open-source project |
| `event` | Follow up before/after an event (pre, post_24h, post_week) |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure `.env`

```
GROQ_API_KEY=your_groq_api_key
GMAIL_ADDRESS=your_gmail@gmail.com
GMAIL_APP_PASSWORD=your_app_password
GROQ_MODEL=llama-3.3-70b-versatile
DAILY_SEND_CAP=30
MIN_DELAY_SEC=30
MAX_DELAY_SEC=90
```

- Get a Groq API key at [console.groq.com](https://console.groq.com)
- Generate a Gmail App Password: Google Account → Security → 2-Step Verification → App Passwords

### 3. Fill in `profile.json`

Edit all `<fill>` fields with your real information. The app will refuse to send if any `<fill>` remains.

```json
{
  "name": "Your Name",
  "one_liner": "Your one-liner",
  "email": "your@email.com",
  "github": "https://github.com/you",
  "linkedin": "https://linkedin.com/in/you",
  "portfolio": "",
  "goals": "What you're looking for",
  "projects": [
    {
      "name": "Project Name",
      "url": "https://github.com/you/project",
      "summary": "One factual line about the project",
      "tags": ["relevant", "tags"]
    }
  ]
}
```

### 4. Add leads to `leads.csv`

| Column | Required | Notes |
|---|---|---|
| `company` | yes | Firm name |
| `website` | yes | Homepage URL |
| `person_name` | yes | First + last name |
| `person_role` | no | e.g. "CTO", "Engineer" |
| `email` | no | Only if public/official; blank → goes to `needs_manual.csv` |
| `linkedin` | no | Profile URL (for manual outreach note) |
| `category` | yes | One of: `openings`, `contribute`, `connect`, `advice`, `event`, `opensource` |
| `goal` | yes | Your one-line goal for this lead |
| `hook_notes` | no | Personal context: "met at X", a specific repo, a blog post |
| `extra_urls` | no | `;`-separated extra pages to scrape |
| `event_name` | event only | Name of the event |
| `event_phase` | event only | `pre`, `post_24h`, or `post_week` |

Example:
```csv
company,website,person_name,person_role,email,linkedin,category,goal,hook_notes,extra_urls,event_name,event_phase
Acme AI,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,"AI agents internship","Saw their agent-eval launch post",https://acme.ai/blog/evals,,
```

## Workflow

### Step 1: Generate drafts (dry-run, default)

```bash
python agent.py                       # process all leads
python agent.py --category openings   # only one category
python agent.py --limit 5             # at most 5 leads
```

This scrapes sites, extracts facts, drafts emails, validates them, and writes to `drafts.csv`. **Nothing is sent.**

### Step 2: Review drafts

Open `drafts.csv` and read the generated emails. Check the `status` column:
- `draft` — ready to approve
- `rejected` — failed validation (see `reject_reasons`)
- `needs_notes` — event follow-up missing hook_notes

```bash
python agent.py --show                # quick table view
```

### Step 3: Approve

```bash
python agent.py --approve a1b2c3 d4e5f6   # approve specific IDs
python agent.py --approve-all              # approve all valid drafts (asks y/N)
```

### Step 4: Send

```bash
python agent.py --send
```

Only sends drafts with `status == approved`. Respects daily cap, random delays between sends, and duplicate protection (same email+category not sent twice within 30 days).

### Step 5: Follow-ups (optional)

After 5+ days with no reply:

```bash
python agent.py --followups            # generate follow-ups (dry-run)
python agent.py --followups --send     # send them
```

Each lead gets at most one follow-up. Never a second.

## Leads without email

If a lead has no `email` but has a `linkedin`, it goes to `needs_manual.csv` with a generated LinkedIn connection message (under 280 characters). You paste it manually.

## Limits and safety

- **Dry-run by default** — must pass `--send` explicitly
- **Daily send cap** — configurable via `DAILY_SEND_CAP` (default 30)
- **Random delays** — between MIN_DELAY_SEC and MAX_DELAY_SEC per send
- **Duplicate protection** — same email+category blocked within 30 days
- **Validation** — every draft is checked for word count, placeholders, banned phrases, specificity, single ask, and proper sign-off
- **No email guessing** — only uses emails explicitly provided in `leads.csv`

## Running tests

```bash
pytest -v
```

Tests cover the validator, CSV loader, project picker, and follow-up timing logic. All tests mock LLM and network calls.

## File structure

```
├── agent.py            # CLI orchestrator
├── scraper.py          # Multi-page Playwright scraper
├── email_writer.py     # Fact extraction + drafting + project picking
├── categories.py       # Per-category prompt config
├── validator.py        # Programmatic draft checks
├── mailer.py           # Gmail SMTP sender
├── profile.json        # Your profile (edit this)
├── leads.csv           # Input leads
├── drafts.csv          # Generated drafts + status (gitignored)
├── needs_manual.csv    # Leads without email (gitignored)
├── .env                # API keys (never commit)
└── requirements.txt
```

## Ethics

Only email people using publicly available contact addresses. Keep emails honest and specific. If a draft could be sent to any other company unchanged, the validator rejects it.
