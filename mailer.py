"""
Email sending abstraction — supports multiple providers.

Provider is auto-detected from environment variables:
  1. AWS SES  — if AWS_SES_REGION is set (uses boto3)
  2. Resend   — if RESEND_API_KEY is set
  3. Console  — fallback, prints to stdout (dev mode)

Usage:
    from mailer import send_email
    send_email("to@example.com", "Subject", "<p>HTML body</p>")
"""

import os


def _get_provider() -> str:
    if os.environ.get('AWS_SES_REGION'):
        return 'ses'
    if os.environ.get('RESEND_API_KEY'):
        return 'resend'
    return 'console'


def send_email(to: str, subject: str, html: str) -> None:
    """Send an email. Raises on failure."""
    provider = _get_provider()

    if provider == 'ses':
        _send_ses(to, subject, html)
    elif provider == 'resend':
        _send_resend(to, subject, html)
    else:
        _send_console(to, subject, html)


def _send_ses(to: str, subject: str, html: str) -> None:
    import boto3
    region = os.environ['AWS_SES_REGION']
    sender = os.environ.get('EMAIL_FROM', 'noreply@localhost')
    client = boto3.client('ses', region_name=region)
    client.send_email(
        Source=sender,
        Destination={'ToAddresses': [to]},
        Message={
            'Subject': {'Data': subject, 'Charset': 'UTF-8'},
            'Body': {'Html': {'Data': html, 'Charset': 'UTF-8'}},
        },
    )


def _send_resend(to: str, subject: str, html: str) -> None:
    import resend
    resend.api_key = os.environ['RESEND_API_KEY']
    sender = os.environ.get('EMAIL_FROM', 'noreply@localhost')
    resend.Emails.send({
        "from": sender,
        "to": to,
        "subject": subject,
        "html": html,
    })


def _send_console(to: str, subject: str, html: str) -> None:
    print(f"\n{'='*60}")
    print(f"EMAIL to {to}")
    print(f"Subject: {subject}")
    print(f"Body: {html}")
    print(f"{'='*60}\n")


def is_configured() -> bool:
    """Return True if a real email provider is configured."""
    return _get_provider() != 'console'
