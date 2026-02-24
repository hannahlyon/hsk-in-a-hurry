"""Email sending for the HSK in a Hurry website (Gmail SMTP)."""
import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

_PDF_PATH = Path(__file__).parent.parent / "posts" / "hsk" / "chengyu700.pdf"

_HTML_BODY = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<style>
  body  {{ font-family: Arial, sans-serif; background: #f8f6fd; margin: 0; padding: 0; }}
  .wrap {{ max-width: 560px; margin: 40px auto; background: #fff;
           border-radius: 12px; overflow: hidden;
           box-shadow: 0 2px 16px rgba(50,50,50,.08); }}
  .top  {{ background: #f8aaa3; padding: 32px 40px; text-align: center; }}
  .top h1 {{ font-size: 1.8rem; color: #323232; margin: 0; font-family: Georgia, serif; }}
  .body {{ padding: 36px 40px; color: #323232; line-height: 1.7; }}
  .body h2 {{ font-family: Georgia, serif; color: #323232; margin-top: 0; }}
  .body p  {{ margin: 0 0 16px; }}
  .cta  {{ display: inline-block; margin: 8px 0 24px;
           background: #f8aaa3; color: #323232; padding: 14px 32px;
           border-radius: 8px; font-weight: bold; text-decoration: none; }}
  .gift {{ background: #fff3b1; border-radius: 8px; padding: 16px 20px;
           margin: 0 0 24px; font-size: .95rem; }}
  .foot {{ border-top: 1px solid #e2ddf7; padding: 20px 40px;
           text-align: center; font-size: .8rem; color: #888; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="top"><h1>HSK in a Hurry 🎉</h1></div>
  <div class="body">
    <h2>Welcome, {name}!</h2>
    <p>You're officially subscribed. Every Monday you'll receive a new Mandarin
    mini-story — complete with vocabulary, grammar, and pinyin — mapped to your
    HSK level.</p>
    <a href="{archive_url}" class="cta">Browse the Archive →</a>
    <div class="gift">
      <strong>🎁 Welcome gift attached</strong><br/>
      We've included <em>700 Chengyu</em> — a curated PDF of 700 classical
      Chinese idioms with meanings and example sentences. A handy reference
      as your Mandarin grows!
    </div>
    <p>Questions? Just reply to this email.</p>
    <p>加油! (Keep going!)<br/><strong>The HSK in a Hurry team</strong></p>
  </div>
  <div class="foot">You're receiving this because you subscribed at {base_url}</div>
</div>
</body>
</html>
"""

_PLAIN_BODY = """\
Welcome to HSK in a Hurry, {name}!

You're officially subscribed. Every Monday you'll receive a new Mandarin
mini-story mapped to your HSK level.

Browse the archive: {archive_url}

We've attached a welcome gift: 700 Chengyu — a curated PDF of 700 classical
Chinese idioms with meanings and example sentences.

Questions? Just reply to this email.

加油! (Keep going!)
The HSK in a Hurry team
"""


def send_welcome_email(to_email: str, to_name: str) -> None:
    """Send a subscription confirmation email with chengyu700.pdf attached."""
    smtp_user = os.getenv("EMAIL_FROM", "")
    smtp_pass = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "")
    base_url  = os.getenv("WEBSITE_BASE_URL", "http://localhost:8001")

    if not smtp_user or not smtp_pass:
        logger.warning("EMAIL_FROM or EMAIL_APP_PASSWORD not set — skipping welcome email")
        return

    archive_url = f"{base_url}/archive"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = "You're subscribed to HSK in a Hurry 🎉"
    msg["From"]    = f"HSK in a Hurry <{smtp_user}>"
    msg["To"]      = to_email

    # Body (HTML + plain fallback)
    body_alt = MIMEMultipart("alternative")
    body_alt.attach(MIMEText(
        _PLAIN_BODY.format(name=to_name, archive_url=archive_url, base_url=base_url),
        "plain", "utf-8",
    ))
    body_alt.attach(MIMEText(
        _HTML_BODY.format(name=to_name, archive_url=archive_url, base_url=base_url),
        "html", "utf-8",
    ))
    msg.attach(body_alt)

    # Attachment
    if _PDF_PATH.exists():
        with open(_PDF_PATH, "rb") as f:
            pdf = MIMEApplication(f.read(), _subtype="pdf")
            pdf.add_header("Content-Disposition", "attachment", filename="chengyu700.pdf")
            msg.attach(pdf)
    else:
        logger.warning("chengyu700.pdf not found at %s — sending without attachment", _PDF_PATH)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_bytes())
        logger.info("Welcome email sent to %s", to_email)
    except smtplib.SMTPException as exc:
        logger.error("Failed to send welcome email to %s: %s", to_email, exc)
        raise
