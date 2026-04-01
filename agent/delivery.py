import os
import logging
from datetime import date
from pathlib import Path

import markdown as md_lib
from jinja2 import Environment, FileSystemLoader

from agent.models import Newsletter

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
NEWSLETTERS_DIR = Path(__file__).parent.parent / "newsletters"


def to_markdown(newsletter: Newsletter, newsletter_name: str = "Weekly Digest") -> str:
    """Render newsletter as Markdown."""
    lines = [
        f"# {newsletter.subject_line}",
        f"*{newsletter_name} · {date.today().isoformat()}*",
        "",
        newsletter.intro_paragraph,
        "",
        "---",
        "",
        "## In Depth",
        "",
    ]
    for d in newsletter.deep_dives:
        lines += [
            f"### {d.title}",
            "",
            d.body,
            "",
            f"*Source: [{d.source_name}]({d.url})*",
            "",
        ]

    if newsletter.summaries:
        lines += ["---", "", "## Also This Week", ""]
        for s in newsletter.summaries:
            lines += [
                f"### {s.title}",
                "",
                s.body,
                "",
                f"*[{s.source_name}]({s.url})*",
                "",
            ]

    if newsletter.quick_links:
        lines += ["---", "", "## Worth a Click", ""]
        for q in newsletter.quick_links:
            lines += [f"- **[{q.title}]({q.url})** ({q.source_name}) — {q.description}"]
        lines += [""]

    lines += ["---", "", newsletter.outro]
    return "\n".join(lines)


def to_html(newsletter: Newsletter, newsletter_name: str = "Weekly Digest") -> str:
    """Render newsletter as HTML email using Jinja2 template."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("email.html")
    return template.render(
        subject=newsletter.subject_line,
        newsletter_name=newsletter_name,
        date=date.today().strftime("%B %d, %Y"),
        intro_paragraph=newsletter.intro_paragraph,
        deep_dives=newsletter.deep_dives,
        summaries=newsletter.summaries,
        quick_links=newsletter.quick_links,
        outro=newsletter.outro,
    )


def save_markdown(content_md: str) -> Path:
    """Write newsletter markdown to newsletters/YYYY-MM-DD.md."""
    NEWSLETTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = NEWSLETTERS_DIR / f"{date.today().isoformat()}.md"
    path.write_text(content_md, encoding="utf-8")
    logger.info("Newsletter saved to %s", path)
    return path


def send_email(
    content_html: str,
    subject: str,
    recipient_email: str | None = None,
    sender_email: str | None = None,
    sender_name: str = "Newsletter Agent",
) -> bool:
    """Send HTML email via Resend. Returns True on success."""
    try:
        import resend  # type: ignore

        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            logger.error("RESEND_API_KEY not set")
            return False

        resend.api_key = api_key

        to = recipient_email or os.environ.get("RECIPIENT_EMAIL")
        from_addr = sender_email or os.environ.get("SENDER_EMAIL")

        if not to:
            logger.error("No recipient email configured")
            return False
        if not from_addr:
            logger.error("No sender email configured")
            return False

        params = {
            "from": f"{sender_name} <{from_addr}>",
            "to": [to],
            "subject": subject,
            "html": content_html,
        }
        resend.Emails.send(params)
        logger.info("Email sent to %s", to)
        return True

    except Exception as e:
        logger.error("Email send failed: %s", e)
        return False


def deliver(
    newsletter: Newsletter,
    method: str = "email",
    newsletter_name: str = "Weekly Digest",
    recipient_email: str | None = None,
    sender_email: str | None = None,
    sender_name: str = "Newsletter Agent",
) -> tuple[str, str, bool]:
    """
    Render and deliver the newsletter.
    Returns (content_md, content_html, delivered_successfully).
    """
    content_md = to_markdown(newsletter, newsletter_name)
    content_html = to_html(newsletter, newsletter_name)

    # Always save markdown as fallback
    save_markdown(content_md)

    delivered = False
    if method == "email":
        delivered = send_email(
            content_html,
            subject=newsletter.subject_line,
            recipient_email=recipient_email,
            sender_email=sender_email,
            sender_name=sender_name,
        )
    elif method == "file":
        delivered = True  # markdown file already saved above
        logger.info("Delivery method is 'file'; newsletter saved to newsletters/")

    return content_md, content_html, delivered
