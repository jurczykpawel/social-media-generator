"""Tests for mailer.py — email via SMTP."""

import os
from unittest.mock import patch, MagicMock

import mailer


def test_is_configured_false(monkeypatch):
    monkeypatch.setenv('SMTP_HOST', '')
    assert mailer.is_configured() is False


def test_is_configured_true(monkeypatch):
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.com')
    assert mailer.is_configured() is True


def test_send_email_dev_mode(monkeypatch, capsys):
    """When SMTP_HOST is empty, email is printed to console."""
    monkeypatch.setenv('SMTP_HOST', '')
    mailer.send_email('user@test.com', 'Test Subject', '<p>Hello</p>')
    captured = capsys.readouterr()
    assert 'user@test.com' in captured.out
    assert 'Test Subject' in captured.out
    assert 'Hello' in captured.out


@patch('mailer.smtplib.SMTP')
def test_send_email_smtp(mock_smtp_class, monkeypatch):
    """When SMTP_HOST is set, email is sent via SMTP."""
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.com')
    monkeypatch.setenv('SMTP_PORT', '587')
    monkeypatch.setenv('SMTP_USER', 'user')
    monkeypatch.setenv('SMTP_PASS', 'pass')
    monkeypatch.setenv('EMAIL_FROM', 'sender@example.com')

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    mailer.send_email('to@example.com', 'Test', '<p>Body</p>')

    mock_smtp_class.assert_called_once_with('smtp.example.com', 587)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with('user', 'pass')
    mock_server.sendmail.assert_called_once()
    args = mock_server.sendmail.call_args[0]
    assert args[0] == 'sender@example.com'
    assert args[1] == ['to@example.com']


@patch('mailer.smtplib.SMTP')
def test_send_email_no_auth(mock_smtp_class, monkeypatch):
    """SMTP without user/pass (some providers allow IP-based auth)."""
    monkeypatch.setenv('SMTP_HOST', 'smtp.internal.com')
    monkeypatch.setenv('SMTP_PORT', '25')
    monkeypatch.setenv('SMTP_USER', '')
    monkeypatch.setenv('SMTP_PASS', '')

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    mailer.send_email('to@example.com', 'Test', '<p>Body</p>')

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_not_called()
    mock_server.sendmail.assert_called_once()
