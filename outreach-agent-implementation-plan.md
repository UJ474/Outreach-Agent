# Outreach Agent v2: Implementation Plan

Hand this whole file to the coding agent. Build on the existing repo (`agent.py`, `scraper.py`, `email_writer.py`, `mailer.py`, `leads.csv`). Keep it a simple Python CLI. No web UI, no database, no background services.

---

## 1. Goal

Turn the current "sales outreach" script into a **personal outreach tool** for reaching specific people at specific firms to:

- ask about **openings** (internships/jobs),
- learn **what they are building** and offer to **contribute** to their work,
- connect with founders/engineers, ask for short advice,
- follow up after **events** (events are just one category, not the whole app).

Every email must be specific to the person and firm, honest about the sender, and contain one clear ask.

## 2. Principles and non-goals

Principles
- Simple: CSV in, CSV out. One command to run.
- Safe by default: **dry-run is the default**. Nothing is sent unless `--send` is passed.
- Specific over generic: an email that could be sent to any other company must be rejected.
- Honest: the model may only use facts from the scraped text and `profile.json`. No invented claims, stats, or projects.

Non-goals (do NOT build)
- No dashboard, no IMAP reply detection, no lead-discovery crawler, no database, no web app, no scheduler/cron, no LinkedIn automation.

## 3. File structure

```
Outreach-Agent/
├── agent.py            # CLI + main loop (orchestrator)
├── scraper.py          # multi-page scraper (upgrade existing)
├── email_writer.py     # fact extraction + drafting + validation (upgrade existing)
├── categories.py       # NEW: per-category prompt config
├── validator.py        # NEW: programmatic checks on drafts
├── mailer.py           # SMTP sender (keep, small changes)
├── profile.json        # NEW: sender profile + projects
├── leads.csv           # input (new schema)
├── drafts.csv          # NEW output: every generated email + status
├── needs_manual.csv    # NEW output: leads with no usable email
├── .env                # keys (never commit)
├── .gitignore
├── requirements.txt
└── README.md           # update
```

`.gitignore` must include `.env`, `drafts.csv`, `needs_manual.csv`, `__pycache__/`, `venv/`.

## 4. Config (`.env`)

```
GROQ_API_KEY=
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
GROQ_MODEL=          # a larger Groq model than llama-3.1-8b; check Groq's current model list and set it here
DAILY_SEND_CAP=30
MIN_DELAY_SEC=30
MAX_DELAY_SEC=90
```

Read all of these in code with sensible defaults. Never hardcode the model name.

## 5. Input: `leads.csv` schema

Columns (header row required):

| column | required | notes |
|---|---|---|
| `company` | yes | firm name |
| `website` | yes | homepage URL |
| `person_name` | yes | first + last name |
| `person_role` | no | e.g. "CTO", "Engineering Manager" |
| `email` | no | only if it is public or official; leave blank otherwise |
| `linkedin` | no | profile URL (used only for the manual-outreach note) |
| `category` | yes | one of: `openings`, `contribute`, `connect`, `advice`, `event`, `opensource` |
| `goal` | yes | the sender's one-line goal for THIS lead, e.g. "AI/agents internship", "contribute to their eval tooling" |
| `hook_notes` | no | anything the sender knows personally: "met at X", "asked about RAG evals", a specific GitHub repo or post to reference |
| `extra_urls` | no | `;`-separated extra pages to scrape (a repo, blog post, docs page) |
| `event_name` | only for `event` | name of the event |
| `event_phase` | only for `event` | `pre`, `post_24h`, `post_week` |

Example rows:

```
company,website,person_name,person_role,email,linkedin,category,goal,hook_notes,extra_urls,event_name,event_phase
Acme AI,https://acme.ai,Jane Roe,CTO,jane@acme.ai,,openings,"AI agents internship","Saw their agent-eval launch post",https://acme.ai/blog/evals,,
Beta Tools,https://beta.dev,Sam Lee,Engineer,,https://linkedin.com/in/samlee,contribute,"contribute to their CLI","Their CLI lacks a --json flag",https://github.com/beta/cli,,
Gamma Conf,https://gamma.io,Priya N,Speaker,priya@gamma.io,,event,"learn from her work on RAG","Her talk on retrieval caching",,Gamma Summit,post_24h
```

Validation on load: skip and report rows missing a required column or with an unknown `category`. Trim whitespace. Dedupe by (`email` or `linkedin`, `category`). Skip any lead already marked `sent` in `drafts.csv`.

## 6. `profile.json` (sender profile)

Single source of truth about the sender. The writer may only claim what is here.

```json
{
  "name": "Utkarsh Jain",
  "one_liner": "B.Tech Data Science student at Newton School of Technology, AI Generalist intern at Newton AI",
  "email": "<fill>",
  "github": "https://github.com/UJ474",
  "linkedin": "<fill>",
  "portfolio": "<fill or empty>",
  "goals": "<fill: e.g. AI/agents or full-stack internship, contributing to real products>",
  "projects": [
    {
      "name": "Newton OOH Agent",
      "url": "https://github.com/UJ474/Newton_OOH_Agent",
      "summary": "<1 line, factual: multi-agent AI media planning platform built during the Newton AI internship>",
      "tags": ["agents", "ai", "llm", "automation", "media", "python"]
    },
    {
      "name": "Hawai",
      "url": "<fill>",
      "summary": "<1 line: full-stack airline booking project>",
      "tags": ["full-stack", "web", "booking"]
    },
    {
      "name": "Outreach Agent",
      "url": "https://github.com/UJ474/Outreach-Agent",
      "summary": "<1 line: scrapes sites, drafts personalized cold emails with an LLM>",
      "tags": ["agents", "scraping", "python", "llm"]
    }
  ],
  "other_proof": ["Competitive programming; CP Club committee member, mentors students in DSA"]
}
```

The sender should edit the `<fill>` fields and each summary so they are accurate. If a field is still `<fill>`, the app must refuse to send (see validator) and print which fields are missing.

## 7. Pipeline per lead

```
load lead
  -> scrape (homepage + up to 3 internal pages + extra_urls)
  -> extract_facts (LLM call 1, JSON output)
  -> pick_projects (simple tag/keyword overlap, no LLM)
  -> draft_email (LLM call 2, category prompt)
  -> validate (programmatic) -> if fails, retry draft ONCE with the failure reasons appended
  -> if still failing: mark status "rejected" with reasons, continue
  -> write to drafts.csv
  -> if --send and status approved path: send via SMTP
```

### 7.1 Scraping (`scraper.py`)

- Keep Playwright, headless Chromium.
- Function `scrape_site(website, extra_urls) -> dict` returning `{url: text}`.
- Pages to try on the same domain, in order, skipping any that 404 or fail: homepage, `/about`, `/blog` or `/news` or `/changelog` (first that works), `/careers` or `/jobs` (first that works). Max 4 internal pages plus all `extra_urls`.
- Per page: wait for `domcontentloaded`; if text under 300 chars, retry once with `networkidle`. Remove `nav, footer, script, style, noscript`. Return up to 2500 chars per page. Total cap 8000 chars per lead.
- Timeout 20 s per page. Never crash the run on a failed page; log and continue.
- Sleep 1-2 s between page loads on the same site. Respect that this is a polite personal tool, not a crawler.
- If a page has `mailto:` links, collect them but do NOT use them automatically (the sender decides). Only the `email` column is used for sending.

### 7.2 Fact extraction (LLM call 1)

Input: scraped text dict + lead row. Output: strict JSON.

System prompt:
```
You extract facts from website text. Use ONLY the text provided. If something is not in the text, use null. Do not guess. Return valid JSON only, no markdown.
```

Required JSON keys:
```json
{
  "what_they_build": "one sentence",
  "recent_news": ["up to 2 concrete items with the page they came from"],
  "tech_or_domain": ["up to 5 technologies or domains explicitly mentioned"],
  "open_roles": ["role titles found on the careers page, or empty list"],
  "hiring_signal": "yes | no | unknown",
  "contribution_ideas": ["up to 2 concrete, small, plausible ideas grounded in the text, each one sentence"],
  "best_hook": "the single most specific thing worth mentioning in an email, with its source page"
}
```

Parse with `json.loads`; on failure, strip code fences and retry once; if still invalid, set all fields null and let the validator block generic drafts.

### 7.3 Project picking (no LLM)

- Build a keyword set from `tech_or_domain`, `what_they_build`, and the lead `goal`.
- Score each project in `profile.json` by number of overlapping tags/keywords (case-insensitive). Pick the top 1 (top 2 only for `openings`). If all scores are 0, use the first project.
- Pass only the chosen projects to the writer.

### 7.4 Drafting (LLM call 2)

Common system prompt (all categories):

```
You write short, genuine cold emails from a student to a professional.
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
<email body, starting with "Hi <first name>," and ending with "Best,\n<sender name>" plus one line with GitHub link>
```

User prompt is assembled from: `PROFILE` (name, one-liner, goals), `PROJECTS` (chosen), `LEAD` (person, role, company, category, goal, hook_notes), `FACTS` (the JSON), and the **category instruction** from `categories.py`.

### 7.5 Category instructions (`categories.py`)

Store as a dict `CATEGORIES = {name: {"instruction": str, "ask": str}}`.

- **openings**
  - Instruction: State the kind of role sought (from GOAL). Connect the best hook about their product to one relevant project. If FACTS lists open_roles, mention the most relevant one by title; if none, say the sender is interested in internship-level work in that area without claiming a posted role.
  - Ask: whether there is an opening, or who the right person to speak with is.
- **contribute**
  - Instruction: Name something specific they are building. Offer ONE concrete contribution taken from `contribution_ideas` or `hook_notes` (a small feature, fix, prototype, or analysis). Say it is small and can start without commitment. Link the most relevant project as proof.
  - Ask: whether a small task, issue, or demo from the sender would be useful.
- **connect**
  - Instruction: Show understanding of what the firm builds in one sentence. Share one short observation or idea. Keep it light, no job ask.
  - Ask: a 15-minute call, or their thoughts on one specific question.
- **advice**
  - Instruction: Ask exactly one specific question tied to the person's own work or path. Mention the sender's goal in one line so the question has context.
  - Ask: a short reply with their view; explicitly no call needed.
- **opensource**
  - Instruction: Refer to the repo or issue in `extra_urls`/`hook_notes`. Say what the sender studied and what they plan to change. Do not claim any work already done unless it is in PROFILE.
  - Ask: whether the approach is welcome before the sender opens a PR.
- **event**
  - Instruction: Use EVENT_NAME and EVENT_PHASE. `pre`: say the sender is looking forward to their session and ask one question. `post_24h`: name one specific takeaway from HOOK_NOTES and what the sender will try because of it, thank them. `post_week`: share one thing the sender built or wrote after the event (only if in PROFILE or HOOK_NOTES).
  - Ask: one specific question, feedback, or staying in touch. If HOOK_NOTES is empty for `post_24h`, mark the lead `needs_notes` and skip drafting (a generic "great talk" email is worse than none).

### 7.6 Follow-ups

- Mode `--followups`: read `drafts.csv`, find rows with status `sent`, `followup_sent` empty, and `sent_at` at least 5 days old (use calendar days; weekends are fine).
- Draft ONE follow-up using the stored original subject/body as context. 50 to 70 words. Add one new angle: a relevant link, a small new idea, or a one-line clarification of the ask. Subject is `Re: <original subject>`.
- Mark `followup_sent` when sent. Never send a second follow-up.

## 8. Validator (`validator.py`)

Function `validate(subject, body, profile, lead) -> list[str]` returning a list of failure reasons (empty means pass). Checks:

1. Body word count between 70 and 140 (follow-ups: 40 to 90).
2. Subject non-empty, 3 to 9 words, no ALL CAPS words, no "!" .
3. No unfilled placeholders: no `[`, `]`, `<`, `>`, `{`, `}`, "TODO", "<fill>".
4. Starts with `Hi <first name>,` using the lead's first name.
5. Contains no banned phrases (the list from 7.4) and none of: "I hope this finds you well", "I am writing to".
6. Contains at least one link that exists in `profile.json` (a chosen project URL or the GitHub URL), and **no URL that is not from `profile.json`, the lead's website, or `extra_urls`**.
7. Contains at least one concrete token from FACTS or HOOK_NOTES (company/product name, technology, or a distinctive noun from `best_hook`). If none, fail with "too generic".
8. Exactly one question mark in the last 3 sentences (single ask).
9. Sender name present in the sign-off.

Also a **pre-run profile check**: if `profile.json` contains the string `<fill>` anywhere, `--send` must abort with a list of missing fields. Dry-run may continue but prints a warning.

On failure: retry the draft once, appending the failure reasons to the user prompt as "Fix these issues:". If it still fails, save to `drafts.csv` with status `rejected` and the reasons.

## 9. Outputs

### `drafts.csv` columns
```
id, created_at, company, person_name, email, category, goal, subject, body,
facts_json, projects_used, status, reject_reasons, sent_at, followup_sent
```
- `id`: short hash of (email or linkedin) + category.
- `status`: one of `draft`, `rejected`, `needs_notes`, `approved`, `sent`, `failed`.
- Append-only; update rows in place by `id` when status changes (rewrite the file safely via a temp file).

### `needs_manual.csv`
For leads with a blank `email`: write `company, person_name, linkedin, category, goal, note`. `note` is a LinkedIn connection message under 280 characters (LLM-generated with the same rules, one specific hook, no ask bigger than a connection). The app never sends these; the sender pastes them manually.

## 10. CLI (`agent.py`)

Use `argparse`:

```
python agent.py                         # dry-run: generate drafts only (default)
python agent.py --send                  # send drafts that are status "approved"
python agent.py --approve <id> [<id>..] # mark drafts approved
python agent.py --approve-all           # mark all valid drafts approved (asks "y/N")
python agent.py --category openings     # only process this category
python agent.py --limit 5               # process at most N leads
python agent.py --followups             # generate due follow-ups (dry-run)
python agent.py --followups --send      # send approved follow-ups
python agent.py --show                  # print a table: id, person, category, status
```

Workflow the user follows: run dry-run, open `drafts.csv`, read emails, run `--approve <ids>`, then `--send`.

Console output per lead, concise:
```
[3/12] Jane Roe @ Acme AI (openings)
  scraped 4 pages (6,210 chars)
  facts ok | projects: Newton OOH Agent
  draft ok (104 words) -> id a1b2c3
```

## 11. Sending rules (`mailer.py`)

- Keep Gmail SMTP over SSL (port 465) with app password.
- Send only rows with `status == approved` and a non-empty `email`.
- Plain-text emails; set `From` to the sender's name + address; add a `Reply-To`.
- Randomized sleep `uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)` between sends.
- Stop when `DAILY_SEND_CAP` is reached (count rows with today's `sent_at`).
- On exception: status `failed`, store the error, continue. Return True/False as now.
- Never send to the same email twice for the same category. Never send a lead's initial email if the same email has any `sent` row within the last 30 days.
- Do not guess or construct email addresses anywhere in the code.

## 12. Error handling and logging

- Wrap each lead in try/except; one bad lead must not stop the run.
- Use Python `logging` to a file `agent.log` plus short console output.
- Retry Groq calls up to 3 times with exponential backoff (2s, 4s, 8s) on rate-limit/5xx errors.
- Keep each LLM call under about 1500 input tokens (truncate scraped text accordingly) and `max_tokens` around 400 for emails, 500 for facts. `temperature` 0.2 for fact extraction, 0.6 for drafting.

## 13. Build order and acceptance criteria

1. **Schema and profile.** New `leads.csv` loader with validation; `profile.json` loader; `drafts.csv` read/write helpers.
   - Done when: bad rows are reported, good rows load, dedupe works.
2. **Scraper upgrade.** Multi-page scraping with caps and timeouts.
   - Done when: running on 3 sample sites returns text for at least 2 pages each without crashing on a 404.
3. **Fact extraction.** LLM call 1 plus JSON parsing.
   - Done when: output matches the schema, nulls where text lacks info.
4. **Project picking + category prompts + drafting.**
   - Done when: each of the 6 categories produces a correctly formatted `SUBJECT`/`BODY`.
5. **Validator + single retry.**
   - Done when: unit tests (see below) pass and generic drafts get rejected.
6. **Dry-run flow + CLI flags + drafts.csv.**
   - Done when: `python agent.py --limit 3` produces drafts and sends nothing.
7. **Approve + send flow with caps and delays.**
   - Done when: only approved drafts send; cap and duplicate rules enforced.
8. **needs_manual.csv for leads without email.**
9. **Follow-ups.**
10. **README update** with setup, CSV schema, workflow, and a sample.

## 14. Tests (keep small, use `pytest`)

- `test_validator.py`: passes a good draft; fails on each of: too short, placeholder text, banned phrase, unknown URL, no concrete token, two asks.
- `test_loader.py`: missing column, unknown category, duplicate rows, blank email goes to manual list.
- `test_project_pick.py`: tag overlap picks the expected project.
- `test_followup_due.py`: due only after 5 days and only once.
- Mock the Groq and SMTP calls in tests; no network in tests.

## 15. README additions

Document: purpose, the 6 categories with one-line meaning each, `.env` setup, `profile.json` fields, `leads.csv` columns and examples, the dry-run, approve, send workflow, limits (daily cap, one follow-up), and a note: "Only email people using publicly available contact addresses; keep emails honest and specific."

## 16. Definition of done

- Running with the sample leads (one per category) generates six distinct, specific drafts in `drafts.csv` with no sends.
- Every draft passes the validator or is marked `rejected` with reasons.
- `--approve` then `--send` sends only approved drafts, respecting delay, cap, and duplicate rules.
- Leads without an email land in `needs_manual.csv` with a LinkedIn note.
- No code path constructs or guesses email addresses.
