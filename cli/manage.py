"""
CLI management tool for the newsletter agent.

Usage:
    python -m cli.manage <command> [args]

Commands:
    add-topic <name>          Add an interest topic
    remove-topic <name>       Remove an interest topic
    list-topics               List all topics

    add-source <url> <name>   Add an RSS source
    disable-source <id>       Disable a source by ID
    list-sources              List all sources with quality scores

    preview                   Generate newsletter without sending (dry run)
    show-last                 Print the last sent newsletter
    run                       Run the full pipeline (send newsletter)
    discover                  Run source discovery manually
"""
import sys
import os
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from db import database


@click.group()
def cli():
    """Newsletter Agent management CLI."""
    database.initialize()


# ── Topics ───────────────────────────────────────────────────────────────────

@cli.command("add-topic")
@click.argument("name")
def add_topic(name: str):
    """Add an interest topic."""
    database.add_topic(name)
    click.echo(f"Added topic: {name.lower().strip()}")


@cli.command("remove-topic")
@click.argument("name")
def remove_topic(name: str):
    """Remove an interest topic."""
    if database.remove_topic(name):
        click.echo(f"Removed topic: {name.lower().strip()}")
    else:
        click.echo(f"Topic not found or already inactive: {name}", err=True)


@cli.command("list-topics")
def list_topics():
    """List all topics."""
    topics = database.list_all_topics()
    if not topics:
        click.echo("No topics configured yet. Use 'add-topic' to add some.")
        return
    click.echo(f"{'ID':<4} {'Active':<8} {'Name'}")
    click.echo("-" * 40)
    for t in topics:
        active = "✓" if t["active"] else "✗"
        click.echo(f"{t['id']:<4} {active:<8} {t['name']}")


# ── Sources ──────────────────────────────────────────────────────────────────

@cli.command("add-source")
@click.argument("url")
@click.argument("name")
def add_source(url: str, name: str):
    """Add an RSS feed source."""
    database.add_source(url, name)
    click.echo(f"Added source: {name} ({url})")


@cli.command("disable-source")
@click.argument("source_id", type=int)
def disable_source(source_id: int):
    """Disable a source by its ID."""
    if database.disable_source(source_id):
        click.echo(f"Disabled source ID {source_id}")
    else:
        click.echo(f"Source ID {source_id} not found.", err=True)


@cli.command("list-sources")
@click.option("--all", "show_all", is_flag=True, help="Include inactive sources")
def list_sources(show_all: bool):
    """List sources with quality scores."""
    sources = database.list_all_sources()
    if not show_all:
        sources = [s for s in sources if s["active"]]
    if not sources:
        click.echo("No sources configured.")
        return
    click.echo(f"{'ID':<4} {'Score':<7} {'Auto':<6} {'Active':<8} {'Name':<30} URL")
    click.echo("-" * 90)
    for s in sources:
        auto = "auto" if s["auto_discovered"] else "user"
        active = "✓" if s["active"] else "✗"
        name = s["name"][:28]
        click.echo(f"{s['id']:<4} {s['quality_score']:.2f}  {auto:<6} {active:<8} {name:<30} {s['url']}")


# ── Pipeline ─────────────────────────────────────────────────────────────────

@cli.command("preview")
def preview():
    """Generate a newsletter without sending it (dry run)."""
    from agent.pipeline import run
    run(dry_run=True)


@cli.command("run")
def run_pipeline():
    """Run the full pipeline (generate and send newsletter)."""
    from agent.pipeline import run
    run(dry_run=False)


@cli.command("show-last")
def show_last():
    """Print the last sent newsletter."""
    newsletter = database.get_last_newsletter()
    if not newsletter:
        click.echo("No newsletters sent yet.")
        return
    click.echo(f"[Sent: {newsletter['run_at']}]")
    click.echo()
    click.echo(newsletter["content_md"] or "(no content stored)")


@cli.command("discover")
def discover():
    """Run source discovery manually."""
    from agent.discoverer import discover as run_discover
    topics = database.get_active_topics()
    if not topics:
        click.echo("No active topics. Add topics first.", err=True)
        return
    click.echo(f"Running source discovery for topics: {', '.join(topics)}")
    run_discover(topics)
    click.echo("Done.")


if __name__ == "__main__":
    cli()
