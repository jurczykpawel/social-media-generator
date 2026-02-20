"""
Email sending via SMTP — works with any provider.

Configure in .env:
    SMTP_HOST=email-smtp.eu-central-1.amazonaws.com   # AWS SES
    SMTP_PORT=587
    SMTP_USER=AKIA...
    SMTP_PASS=...
    EMAIL_FROM=login@yourdomain.com

Works out of the box with: AWS SES, Resend, Mailgun, SendGrid,
Postmark, any SMTP server.

If SMTP_HOST is not set → dev mode (prints to console).
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(to: str, subject: str, html: str) -> None:
    """Send an email via SMTP. Raises on failure."""
    host = os.environ.get('SMTP_HOST', '')
    if not host:
        _send_console(to, subject, html)
        return

    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER', '')
    password = os.environ.get('SMTP_PASS', '')
    sender = os.environ.get('EMAIL_FROM', 'noreply@localhost')

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        if user:
            server.login(user, password)
        server.sendmail(sender, [to], msg.as_string())


def _send_console(to: str, subject: str, html: str) -> None:
    print(f"\n{'='*60}")
    print(f"EMAIL to {to}")
    print(f"Subject: {subject}")
    print(f"Body: {html}")
    print(f"{'='*60}\n")


def is_configured() -> bool:
    """Return True if SMTP is configured (not dev mode)."""
    return bool(os.environ.get('SMTP_HOST'))
