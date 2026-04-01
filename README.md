# Newsletter Agent

An AI-powered weekly newsletter that fetches, ranks, and summarizes news on topics you care about. Runs automatically via GitHub Actions every Monday.

## Quick Start

```bash
# Install dependencies
pip install uv
uv pip install -e .

# Add your interests
python -m cli.manage add-topic "artificial intelligence"
python -m cli.manage add-topic "climate science"
python -m cli.manage add-topic "space exploration"

# Preview a newsletter (no email sent)
ANTHROPIC_API_KEY=sk-... python -m cli.manage preview
```

## Setup

### 1. Configure settings

Edit `config/settings.toml`:
- Set `recipient_email` and `sender_email` (or use env vars)
- Adjust `deep_dive_count`, `summary_count`, `max_words` as needed

### 2. Set up Resend (email delivery)

1. Sign up at [resend.com](https://resend.com) (free tier: 3,000 emails/month)
2. Verify a sending domain or use the sandbox for testing
3. Get your API key

### 3. Deploy to GitHub

1. Push this repo to GitHub (can be private)
2. Add secrets in **Settings → Secrets and variables → Actions**:
   - `ANTHROPIC_API_KEY`
   - `RESEND_API_KEY`
   - `RECIPIENT_EMAIL`
   - `SENDER_EMAIL`
   - `NEWSAPI_KEY` (optional, for source discovery — get at newsapi.org)
3. The newsletter runs every Monday at 8am UTC
4. Trigger a manual run anytime via **Actions → Weekly Newsletter → Run workflow**

## Managing Topics & Sources

```bash
# Topics
python -m cli.manage add-topic "quantum computing"
python -m cli.manage remove-topic "quantum computing"
python -m cli.manage list-topics

# Sources
python -m cli.manage list-sources             # see quality scores
python -m cli.manage disable-source 3        # remove a source by ID
python -m cli.manage add-source <url> <name> # add a custom RSS feed

# Newsletter
python -m cli.manage preview                  # dry run
python -m cli.manage show-last                # print last newsletter
python -m cli.manage run                      # send now
```

## How It Works

1. **Fetch** — Pulls articles from RSS feeds (last 8 days, up to 500 articles)
2. **Deduplicate** — Hashes URLs and compares titles to remove repeats and cross-posted stories
3. **Score** — Claude rates each article's relevance to your topics (0–1)
4. **Select** — Top 3 become deep dives (~300 words); next 10 become brief summaries (~80 words); diversity cap prevents topic overload
5. **Write** — Claude generates the full newsletter (≤2,100 words ≈ 14 min read)
6. **Deliver** — Sent via Resend email + saved as `newsletters/YYYY-MM-DD.md` in the repo
7. **Remember** — Article hashes, source quality scores, and topic coverage saved to `data/memory.db`
8. **Discover** (monthly) — NewsAPI finds new source candidates; Claude evaluates quality

## Project Structure

```
agent/          Core pipeline (fetcher, deduplicator, scorer, selector, writer, delivery)
cli/            Management CLI (manage.py)
config/         settings.toml
db/             SQLite schema + query helpers
templates/      HTML email template
data/           memory.db (SQLite, committed to repo = persistent state)
newsletters/    Past newsletters as markdown files
.github/        GitHub Actions workflow
```

## Cost

~$0.03/newsletter in Claude API costs. Everything else on free tiers. ~$1.50/year total.
