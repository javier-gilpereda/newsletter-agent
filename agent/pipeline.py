"""
Main pipeline orchestrator. Run with:
    python -m agent.pipeline
"""
import json
import logging
import os
import sys
import tomllib
from pathlib import Path
from collections import defaultdict

from db import database
from agent import fetcher, deduplicator, scorer, selector, writer, delivery, discoverer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.toml"


def load_config() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def run(dry_run: bool = False):
    logger.info("=== Newsletter Agent Starting%s ===", " (DRY RUN)" if dry_run else "")

    # Initialize DB
    database.initialize()

    cfg = load_config()
    nl_cfg = cfg["newsletter"]
    del_cfg = cfg["delivery"]
    disc_cfg = cfg.get("discovery", {})

    # Load topics
    topics = database.get_active_topics()
    if not topics:
        logger.error("No active topics configured. Add some with: python -m cli.manage add-topic <topic>")
        sys.exit(1)
    logger.info("Active topics: %s", topics)

    # Step 1: Fetch
    articles = fetcher.fetch_all(
        lookback_days=nl_cfg.get("lookback_days", 8),
        max_per_source=50,
        max_total=500,
    )
    logger.info("Fetched %d raw articles", len(articles))

    # Step 2: Deduplicate
    unique_articles = deduplicator.deduplicate(articles)
    if not unique_articles:
        logger.warning("No new articles after deduplication. Nothing to send.")
        sys.exit(0)

    # Step 3: Score
    recent_coverage = database.get_recent_coverage(n_runs=2)
    scored_articles = scorer.score(unique_articles, topics, recent_coverage)
    if not scored_articles:
        logger.warning("No relevant articles found after scoring.")
        sys.exit(0)
    logger.info("Scored: %d relevant articles", len(scored_articles))

    # Step 4: Select
    selected = selector.select(
        scored_articles,
        deep_dive_count=nl_cfg.get("deep_dive_count", 3),
        summary_count=nl_cfg.get("summary_count", 10),
        max_per_topic=nl_cfg.get("max_topic_per_section", 2),
    )

    # Step 5: Write
    newsletter = writer.write(selected, topics)
    logger.info("Newsletter: '%s' (%d words)", newsletter.subject_line, newsletter.estimated_word_count)

    if dry_run:
        md = delivery.to_markdown(newsletter, del_cfg.get("name", "Weekly Digest"))
        print("\n" + "="*60)
        print(md)
        print("="*60)
        print(f"\n[DRY RUN] Would send to: {del_cfg.get('recipient_email') or os.environ.get('RECIPIENT_EMAIL', '(not configured)')}")
        return

    # Step 6: Deliver
    content_md, content_html, delivered = delivery.deliver(
        newsletter,
        method=del_cfg.get("method", "email"),
        newsletter_name=del_cfg.get("name", "Weekly Digest"),
        recipient_email=del_cfg.get("recipient_email") or None,
        sender_email=del_cfg.get("sender_email") or None,
        sender_name=del_cfg.get("sender_name", "Newsletter Agent"),
    )

    # Step 7: Persist state
    topics_snapshot = json.dumps(topics)
    run_id = database.create_run(topics_snapshot)

    all_used = selected.deep_dives + selected.summaries
    used_hashes = [a.raw.url_hash for a in all_used]
    score_map = {a.raw.url_hash: a.relevance_score for a in all_used}

    database.mark_articles_seen(used_hashes, run_id, score_map)

    # Update source quality scores
    source_signals: dict[int, list[float]] = defaultdict(list)
    for a in scored_articles:
        source_signals[a.raw.source_id].append(a.relevance_score)
    for source_id, signals in source_signals.items():
        avg_signal = sum(signals) / len(signals)
        database.update_source_quality(source_id, avg_signal)

    # Save topic coverage
    topic_counts: dict[str, int] = defaultdict(int)
    for a in all_used:
        for tag in (a.topic_tags or ["general"]):
            topic_counts[tag] += 1
    database.save_topic_coverage(run_id, dict(topic_counts))

    database.finalize_run(run_id, len(all_used), content_md, content_html, delivered, del_cfg.get("method", "email"))

    # Step 8: Source discovery (monthly)
    if disc_cfg.get("enabled", True):
        completed_runs = database.count_completed_runs()
        every_n = disc_cfg.get("run_every_n_weeks", 4)
        if completed_runs % every_n == 0:
            logger.info("Running source discovery (run #%d)", completed_runs)
            discoverer.discover(topics)

    logger.info("=== Done. Delivered: %s ===", delivered)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print newsletter without sending")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
