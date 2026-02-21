"""Tests for app.py — API routes, auth, panel, webhook."""

import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock


# ── Health ─────────────────────────────────────────────

def test_health(test_client):
    r = test_client.get('/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok'}


# ── Root redirect ──────────────────────────────────────

def test_root_redirects_to_login(test_client):
    r = test_client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/auth/login' in r.headers['location']


def test_root_redirects_to_panel_when_logged_in(session_client):
    client, user, csrf = session_client
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/panel' in r.headers['location']


# ══════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════

def test_login_page(test_client):
    r = test_client.get('/auth/login')
    assert r.status_code == 200
    assert 'email' in r.text.lower()


def _get_login_csrf(test_client):
    """Helper: extract CSRF token from login page."""
    r = test_client.get('/auth/login')
    import re
    match = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
    return match.group(1) if match else ""


def test_login_submit_sends_magic_link(test_client, tmp_db):
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login', data={'email': 'new@example.com', '_csrf': csrf})
    assert r.status_code == 200
    assert 'Check' in r.text or 'Dev mode' in r.text or 'console' in r.text.lower()


def test_login_submit_without_csrf_rejected(test_client):
    """Login POST without CSRF token is rejected."""
    r = test_client.post('/auth/login', data={'email': 'test@example.com'})
    assert r.status_code == 403


def test_login_invalid_email(test_client):
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login', data={'email': 'not-an-email', '_csrf': csrf})
    assert r.status_code == 200
    assert 'invalid' in r.text.lower() or 'Invalid' in r.text


def test_verify_magic_link(test_client, tmp_db):
    token = tmp_db.create_magic_link('verify@example.com')
    r = test_client.get(f'/auth/verify?token={token}', follow_redirects=False)
    assert r.status_code == 302
    assert '/panel' in r.headers['location']
    assert 'session' in r.cookies


def test_verify_invalid_token(test_client):
    r = test_client.get('/auth/verify?token=bogus', follow_redirects=False)
    assert r.status_code == 400


def test_logout(session_client):
    client, user, csrf = session_client
    r = client.post('/auth/logout', data={'_csrf': csrf}, follow_redirects=False)
    assert r.status_code == 302
    assert '/auth/login' in r.headers['location']


# ══════════════════════════════════════════════════════
# API — Bearer token auth
# ══════════════════════════════════════════════════════

def test_api_no_auth(test_client):
    r = test_client.get('/api/credits')
    assert r.status_code == 401


def test_api_bad_token(test_client):
    r = test_client.get('/api/credits', headers={'Authorization': 'Bearer wrong'})
    assert r.status_code == 401


def test_api_credits(authed_client):
    client, user = authed_client
    r = client.get('/api/credits', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    assert r.json()['credits'] == 100


def test_api_templates(authed_client):
    client, user = authed_client
    r = client.get('/api/templates', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    templates = r.json()['templates']
    assert 'quote-card' in templates


def test_api_brands(authed_client):
    client, user = authed_client
    r = client.get('/api/brands', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    data = r.json()
    assert 'user_brands' in data
    assert 'builtin_brands' in data
    assert 'example' in data['builtin_brands']


@patch('app.render_image', return_value=b'\x89PNG\r\n\x1a\nfake-png-data')
def test_api_generate_single(mock_render, authed_client, tmp_db):
    client, user = authed_client
    r = client.post('/api/generate',
        json={
            'brand': 'example',
            'template': 'quote-card',
            'size': 'post',
            'text': 'Hello',
            'attr': 'Test',
        },
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 200
    assert r.headers['content-type'] == 'image/png'
    mock_render.assert_called_once()
    # Credits deducted
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 99


@patch('app.render_image', return_value=b'\x89PNG\r\n\x1a\nfake-png-data')
def test_api_generate_all_sizes(mock_render, authed_client, tmp_db):
    client, user = authed_client
    r = client.post('/api/generate',
        json={
            'brand': 'example',
            'template': 'quote-card',
            'size': 'all',
            'text': 'Hello',
        },
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 200
    assert r.headers['content-type'] == 'application/zip'
    assert mock_render.call_count == 3
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 97  # 3 credits for 3 sizes


@patch('app.render_image', return_value=b'\x89PNG\r\n\x1a\nfake-png')
def test_api_generate_insufficient_credits(mock_render, authed_client, tmp_db):
    client, user = authed_client
    # Set credits to 0
    tmp_db.deduct_credits(user['id'], 100, 'drain')
    r = client.post('/api/generate',
        json={'brand': 'example', 'template': 'quote-card', 'size': 'post', 'text': 'X'},
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 402


def test_api_generate_bad_template(authed_client):
    client, user = authed_client
    r = client.post('/api/generate',
        json={'brand': 'example', 'template': 'nonexistent', 'size': 'post', 'text': 'X'},
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 400


def test_api_generate_bad_brand(authed_client):
    client, user = authed_client
    r = client.post('/api/generate',
        json={'brand': 'nonexistent', 'template': 'quote-card', 'size': 'post', 'text': 'X'},
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 400


def test_api_generate_bad_size(authed_client):
    client, user = authed_client
    r = client.post('/api/generate',
        json={'brand': 'example', 'template': 'quote-card', 'size': 'banana', 'text': 'X'},
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════
# Panel — session cookie auth
# ══════════════════════════════════════════════════════

def test_panel_requires_auth(test_client):
    r = test_client.get('/panel', follow_redirects=False)
    assert r.status_code == 302
    assert '/auth/login' in r.headers['location']


def test_panel_dashboard(session_client):
    client, user, csrf = session_client
    r = client.get('/panel')
    assert r.status_code == 200
    assert 'Dashboard' in r.text
    # Token should NOT be fully exposed in DOM
    assert f'value="{user["api_token"]}"' not in r.text


def test_panel_brands_page(session_client):
    client, user, csrf = session_client
    r = client.get('/panel/brands')
    assert r.status_code == 200
    assert 'example' in r.text.lower()


def test_panel_brand_builder_page(session_client):
    client, user, csrf = session_client
    r = client.get('/panel/brands/builder')
    assert r.status_code == 200


def test_panel_brand_builder_save(session_client, tmp_db):
    client, user, csrf = session_client
    r = client.post('/panel/brands/builder',
        data={
            '_csrf': csrf,
            'brand_name': 'my-new-brand',
            'display_name': 'My New Brand',
            'tagline': 'Test tagline',
            'theme': 'dark',
            'bg_primary': '#111111',
            'bg_secondary': '#222222',
            'accent': '#00FF00',
            'cta': '#FF0000',
            'cta_text': '#FFFFFF',
            'text_primary': '#EEEEEE',
            'text_secondary': '#AAAAAA',
            'text_muted': '#666666',
            'font_heading': 'Inter',
            'font_body': 'Inter',
            'heading_weight': '700',
            'heading_weight_heavy': '800',
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert '/panel/brands' in r.headers['location']


def test_panel_brand_upload_css(session_client):
    client, user, csrf = session_client
    css_content = b':root { --brand-accent: blue; }'
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('uploaded.css', css_content, 'text/css')},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_panel_brand_upload_non_css(session_client):
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('hack.js', b'alert(1)', 'application/javascript')},
    )
    assert r.status_code == 400


def test_panel_brand_upload_script_in_css(session_client):
    """CSS containing <script is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('evil.css', b'body { } <script>alert(1)</script>', 'text/css')},
    )
    assert r.status_code == 400


def test_panel_brand_upload_import_in_css(session_client):
    """CSS containing @import is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('evil.css', b'@import url("https://evil.com/steal.css");', 'text/css')},
    )
    assert r.status_code == 400


def test_panel_brand_upload_expression_in_css(session_client):
    """CSS containing expression() is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('evil.css', b'body { width: expression(alert(1)); }', 'text/css')},
    )
    assert r.status_code == 400


def test_panel_token_regenerate(session_client, tmp_db):
    client, user, csrf = session_client
    old_token = user['api_token']
    r = client.post('/panel/token/regenerate', data={'_csrf': csrf}, follow_redirects=False)
    assert r.status_code == 302
    updated = tmp_db.get_user(user['id'])
    assert updated['api_token'] != old_token


def test_panel_brand_delete(session_client, tmp_db):
    """Brand delete via POST with CSRF."""
    client, user, csrf = session_client
    # Create a brand first
    from pathlib import Path
    import app as app_module
    brand_dir = app_module.get_user_brands_dir(user['id'])
    (brand_dir / 'deleteme.css').write_text(':root {}')
    # Delete it
    r = client.post('/panel/brands/deleteme/delete', data={'_csrf': csrf}, follow_redirects=False)
    assert r.status_code == 302
    assert not (brand_dir / 'deleteme.css').exists()


def test_panel_token_copy(session_client, tmp_db):
    """Token copy endpoint returns full token via JSON."""
    client, user, csrf = session_client
    r = client.get('/panel/token/copy')
    assert r.status_code == 200
    assert r.json()['token'] == user['api_token']


def test_panel_token_copy_requires_auth(test_client):
    """Token copy requires login."""
    r = test_client.get('/panel/token/copy', follow_redirects=False)
    assert r.status_code == 302


def test_panel_post_without_csrf_rejected(session_client, tmp_db):
    """POST requests without CSRF token are rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/token/regenerate', follow_redirects=False)
    assert r.status_code == 403


# ══════════════════════════════════════════════════════
# Security — path traversal
# ══════════════════════════════════════════════════════

def test_path_traversal_in_brand_name(authed_client):
    """Brand name with .. is rejected."""
    client, user = authed_client
    r = client.post('/api/generate',
        json={'brand': '../../../etc/passwd', 'template': 'quote-card', 'size': 'post', 'text': 'X'},
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 400


def test_path_traversal_in_preview(test_client):
    """Preview route rejects path traversal."""
    r = test_client.get('/preview/template/../../etc/passwd')
    assert r.status_code in (400, 404, 422)


def test_invalid_brand_name_chars(session_client):
    """Brand names with special chars are rejected in builder."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/builder',
        data={
            '_csrf': csrf,
            'brand_name': 'evil<script>',
            'theme': 'dark',
            'bg_primary': '#111111', 'bg_secondary': '#222222',
            'accent': '#00FF00', 'cta': '#FF0000', 'cta_text': '#FFFFFF',
            'text_primary': '#EEEEEE', 'text_secondary': '#AAAAAA', 'text_muted': '#666666',
            'font_heading': 'Inter', 'font_body': 'Inter',
            'heading_weight': '700', 'heading_weight_heavy': '800',
        },
    )
    assert r.status_code == 400


def test_invalid_color_rejected(session_client):
    """Invalid hex color in builder is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/builder',
        data={
            '_csrf': csrf,
            'brand_name': 'testbrand',
            'theme': 'dark',
            'bg_primary': 'not-a-color', 'bg_secondary': '#222222',
            'accent': '#00FF00', 'cta': '#FF0000', 'cta_text': '#FFFFFF',
            'text_primary': '#EEEEEE', 'text_secondary': '#AAAAAA', 'text_muted': '#666666',
            'font_heading': 'Inter', 'font_body': 'Inter',
            'heading_weight': '700', 'heading_weight_heavy': '800',
        },
    )
    assert r.status_code == 400


def test_invalid_font_rejected(session_client):
    """Invalid font in builder is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/builder',
        data={
            '_csrf': csrf,
            'brand_name': 'testbrand',
            'theme': 'dark',
            'bg_primary': '#111111', 'bg_secondary': '#222222',
            'accent': '#00FF00', 'cta': '#FF0000', 'cta_text': '#FFFFFF',
            'text_primary': '#EEEEEE', 'text_secondary': '#AAAAAA', 'text_muted': '#666666',
            'font_heading': 'EvilFont', 'font_body': 'Inter',
            'heading_weight': '700', 'heading_weight_heavy': '800',
        },
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════
# Preview routes
# ══════════════════════════════════════════════════════

def test_preview_template_requires_auth(test_client):
    """Preview template routes require session auth."""
    r = test_client.get('/preview/template/quote-card', follow_redirects=False)
    assert r.status_code == 302


def test_preview_template_css(session_client):
    client, user, csrf = session_client
    r = client.get('/preview/template/_base.css')
    assert r.status_code == 200
    assert 'text/css' in r.headers['content-type']


def test_preview_template_js(session_client):
    client, user, csrf = session_client
    r = client.get('/preview/template/_base.js')
    assert r.status_code == 200
    assert 'javascript' in r.headers['content-type']


def test_preview_template_html(session_client):
    client, user, csrf = session_client
    r = client.get('/preview/template/quote-card')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']


def test_preview_template_not_found(session_client):
    client, user, csrf = session_client
    r = client.get('/preview/template/nonexistent')
    assert r.status_code == 404


def test_preview_brand_css_builtin(test_client):
    r = test_client.get('/preview/brands/example.css')
    assert r.status_code == 200
    assert 'text/css' in r.headers['content-type']


def test_preview_brand_not_found(test_client):
    r = test_client.get('/preview/brands/nonexistent.css')
    assert r.status_code == 404


# ══════════════════════════════════════════════════════
# Downloads
# ══════════════════════════════════════════════════════

def test_download_ai_instructions(session_client):
    client, user, csrf = session_client
    r = client.get('/panel/downloads/ai-instructions')
    assert r.status_code == 200


def test_download_claude_skill(session_client):
    client, user, csrf = session_client
    r = client.get('/panel/downloads/claude-skill')
    assert r.status_code == 200


def test_download_requires_auth(test_client):
    r = test_client.get('/panel/downloads/ai-instructions', follow_redirects=False)
    assert r.status_code == 302


# ══════════════════════════════════════════════════════
# Webhook — credits
# ══════════════════════════════════════════════════════

def test_webhook_no_auth(test_client):
    r = test_client.post('/webhook/credits',
        json={'email': 'x@y.com', 'credits': 100})
    assert r.status_code == 401


def test_webhook_bearer_token(test_client, tmp_db):
    tmp_db.create_user('buyer@example.com', credits=0)
    r = test_client.post('/webhook/credits',
        json={'email': 'buyer@example.com', 'credits': 100, 'reference': 'order_1'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 200
    data = r.json()
    assert data['ok'] is True
    assert data['credits_added'] == 100
    assert data['new_balance'] == 100


def test_webhook_product_mapping(test_client, tmp_db):
    tmp_db.create_user('product@example.com', credits=0)
    r = test_client.post('/webhook/credits',
        json={'email': 'product@example.com', 'product': '500-credits', 'reference': 'order_2'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 200
    assert r.json()['credits_added'] == 500


def test_webhook_hmac_signature(test_client, tmp_db, monkeypatch):
    monkeypatch.setenv('WEBHOOK_HMAC_SECRET', 'test-hmac-secret')
    tmp_db.create_user('hmac@example.com', credits=0)
    payload = json.dumps({'email': 'hmac@example.com', 'credits': 50, 'reference': 'hmac_1'})
    signature = hmac.new(
        b'test-hmac-secret', payload.encode(), hashlib.sha256
    ).hexdigest()
    r = test_client.post('/webhook/credits',
        content=payload,
        headers={
            'Content-Type': 'application/json',
            'X-Webhook-Signature': signature,
        },
    )
    assert r.status_code == 200
    assert r.json()['credits_added'] == 50


def test_webhook_bad_hmac(test_client, monkeypatch):
    monkeypatch.setenv('WEBHOOK_HMAC_SECRET', 'test-hmac-secret')
    payload = json.dumps({'email': 'x@y.com', 'credits': 100})
    r = test_client.post('/webhook/credits',
        content=payload,
        headers={
            'Content-Type': 'application/json',
            'X-Webhook-Signature': 'deadbeef',
        },
    )
    assert r.status_code == 401


def test_webhook_hmac_configured_no_signature_rejected(test_client, monkeypatch):
    """If HMAC is configured, requests without signature header are rejected (no fallthrough to Bearer)."""
    monkeypatch.setenv('WEBHOOK_HMAC_SECRET', 'test-hmac-secret')
    r = test_client.post('/webhook/credits',
        json={'email': 'x@y.com', 'credits': 100},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 401


def test_webhook_gateflow_format(test_client, tmp_db, monkeypatch):
    monkeypatch.setenv('WEBHOOK_HMAC_SECRET', 'test-hmac-secret')
    tmp_db.create_user('gateflow@example.com', credits=10)
    payload = json.dumps({
        'event': 'purchase.completed',
        'data': {
            'customer': {'email': 'gateflow@example.com'},
            'product': {'slug': '100-credits', 'id': 'prod_1'},
            'order': {'amount': 2900, 'sessionId': 'cs_abc'},
        },
    })
    signature = hmac.new(
        b'test-hmac-secret', payload.encode(), hashlib.sha256
    ).hexdigest()
    r = test_client.post('/webhook/credits',
        content=payload,
        headers={
            'Content-Type': 'application/json',
            'X-GateFlow-Signature': signature,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data['credits_added'] == 100
    assert data['new_balance'] == 110


def test_webhook_auto_create_user(test_client, tmp_db):
    """Webhook should auto-create user if email not found."""
    r = test_client.post('/webhook/credits',
        json={'email': 'newbuyer@example.com', 'credits': 200, 'reference': 'first'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 200
    assert r.json()['credits_added'] == 200
    user = tmp_db.get_user_by_email('newbuyer@example.com')
    assert user is not None


def test_webhook_missing_email(test_client):
    r = test_client.post('/webhook/credits',
        json={'credits': 100},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 400


def test_webhook_lookup_by_user_id(test_client, tmp_db):
    """Webhook can identify user by user_id instead of email."""
    user = tmp_db.create_user('userid-test@example.com', credits=10)
    r = test_client.post('/webhook/credits',
        json={'user_id': user['id'], 'credits': 75, 'reference': 'by-id'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 200
    data = r.json()
    assert data['credits_added'] == 75
    assert data['new_balance'] == 85
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 85


def test_webhook_email_resolves_existing_user(test_client, tmp_db):
    """Webhook with email finds existing user and adds credits to their account."""
    user = tmp_db.create_user('existing@example.com', credits=30)
    r = test_client.post('/webhook/credits',
        json={'email': 'existing@example.com', 'credits': 50, 'reference': 'topup'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 200
    assert r.json()['new_balance'] == 80
    # Verify it's the same user (not a new one)
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 80
    assert updated['id'] == user['id']


def test_webhook_replay_protection(test_client, tmp_db):
    """Duplicate webhook with same reference returns duplicate=True without adding credits."""
    tmp_db.create_user('replay@example.com', credits=0)
    payload = {'email': 'replay@example.com', 'credits': 100, 'reference': 'unique_ref_1'}
    headers = {'Authorization': 'Bearer test-webhook-secret'}
    # First call
    r1 = test_client.post('/webhook/credits', json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.json()['credits_added'] == 100
    # Replay
    r2 = test_client.post('/webhook/credits', json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.json()['duplicate'] is True
    assert r2.json()['credits_added'] == 0
    # Balance unchanged
    user = tmp_db.get_user_by_email('replay@example.com')
    assert user['credits'] == 100


# ══════════════════════════════════════════════════════
# DB — reference_exists
# ══════════════════════════════════════════════════════

def test_reference_exists(tmp_db):
    user = tmp_db.create_user('ref@example.com', credits=0)
    assert tmp_db.reference_exists(user['id'], 'order_99') is False
    tmp_db.add_credits(user['id'], 50, 'order_99')
    assert tmp_db.reference_exists(user['id'], 'order_99') is True


# ══════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════

def test_hex_to_rgba():
    from app import _hex_to_rgba
    assert _hex_to_rgba('#FF0000', 0.5) == 'rgba(255, 0, 0, 0.5)'
    assert _hex_to_rgba('#00FF00', 1.0) == 'rgba(0, 255, 0, 1.0)'
    assert _hex_to_rgba('2DD4BF', 0.12) == 'rgba(45, 212, 191, 0.12)'


# ══════════════════════════════════════════════════════
# Engine — size validation
# ══════════════════════════════════════════════════════

def test_custom_size_valid():
    from engine import parse_size
    result = parse_size('800x600')
    assert result == [('custom', 800, 600)]


def test_custom_size_max_limit():
    from engine import parse_size
    import pytest
    with pytest.raises(ValueError, match="4096"):
        parse_size('5000x5000')


def test_custom_size_zero():
    from engine import parse_size
    import pytest
    with pytest.raises(ValueError, match="4096"):
        parse_size('0x0')


# ══════════════════════════════════════════════════════
# DB — magic link atomicity
# ══════════════════════════════════════════════════════

def test_magic_link_cannot_be_used_twice(tmp_db):
    """Magic link used twice returns None the second time (atomic)."""
    token = tmp_db.create_magic_link('atomic@example.com')
    # First verify succeeds
    email = tmp_db.verify_magic_link(token)
    assert email == 'atomic@example.com'
    # Second verify fails
    email2 = tmp_db.verify_magic_link(token)
    assert email2 is None


# ══════════════════════════════════════════════════════
# Security — API field limits
# ══════════════════════════════════════════════════════

def test_api_generate_text_too_long(authed_client):
    """Text field exceeding max_length is rejected."""
    client, user = authed_client
    r = client.post('/api/generate',
        json={
            'brand': 'example',
            'template': 'quote-card',
            'size': 'post',
            'text': 'X' * 2001,
        },
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 422


def test_api_generate_template_name_sanitized(authed_client):
    """Template name with path traversal chars is rejected."""
    client, user = authed_client
    r = client.post('/api/generate',
        json={
            'brand': 'example',
            'template': '../../../etc/passwd',
            'size': 'post',
            'text': 'X',
        },
        headers={'Authorization': f'Bearer {user["api_token"]}'},
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════
# DB — atomic credits
# ══════════════════════════════════════════════════════

def test_add_credits_atomic_success(tmp_db):
    """add_credits_atomic adds credits and returns True on first call."""
    user = tmp_db.create_user('atomic@example.com', credits=0)
    result = tmp_db.add_credits_atomic(user['id'], 100, 'order_atomic_1')
    assert result is True
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 100


def test_add_credits_atomic_replay(tmp_db):
    """add_credits_atomic returns False on duplicate reference (same transaction safety)."""
    user = tmp_db.create_user('atomic2@example.com', credits=0)
    assert tmp_db.add_credits_atomic(user['id'], 100, 'order_dup') is True
    assert tmp_db.add_credits_atomic(user['id'], 100, 'order_dup') is False
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 100  # Not 200


# ══════════════════════════════════════════════════════
# Token regeneration rate limit
# ══════════════════════════════════════════════════════

def test_token_regenerate_rate_limited(session_client, tmp_db):
    """Token regeneration is rate limited to 5/hour."""
    client, user, csrf = session_client
    from app import _rate_limits
    # Prefill rate limit to simulate 5 recent regenerations
    import time
    _rate_limits[f"token_regen:{user['id']}"] = [time.time()] * 5
    r = client.post('/panel/token/regenerate', data={'_csrf': csrf}, follow_redirects=False)
    assert r.status_code == 429


# ══════════════════════════════════════════════════════
# Magic link cleanup
# ══════════════════════════════════════════════════════

def test_cleanup_expired_links(tmp_db):
    """cleanup_expired_links removes used and expired links."""
    # Create a used link
    token1 = tmp_db.create_magic_link('clean1@example.com')
    tmp_db.verify_magic_link(token1)  # mark as used
    # Create an active link (should survive cleanup)
    token2 = tmp_db.create_magic_link('clean2@example.com')
    tmp_db.cleanup_expired_links()
    # Used link should be gone
    assert tmp_db.verify_magic_link(token1) is None
    # Active link should still work
    assert tmp_db.verify_magic_link(token2) == 'clean2@example.com'


# ══════════════════════════════════════════════════════
# Webhook auth — Bearer constant-time comparison
# ══════════════════════════════════════════════════════

def test_webhook_bearer_wrong_token(test_client):
    """Wrong Bearer token is rejected."""
    r = test_client.post('/webhook/credits',
        json={'email': 'x@y.com', 'credits': 100},
        headers={'Authorization': 'Bearer wrong-token'},
    )
    assert r.status_code == 401


# ══════════════════════════════════════════════════════
# Session invalidation on logout
# ══════════════════════════════════════════════════════

def test_session_invalidated_after_logout(test_client, tmp_db):
    """Old session cookie stops working after logout."""
    from itsdangerous import URLSafeTimedSerializer
    signer = URLSafeTimedSerializer('test-secret-key')

    user = tmp_db.create_user('logout-test@example.com', credits=10)
    version = user.get('session_version', 1)
    session_token = signer.dumps(f"{user['id']}:{version}")
    test_client.cookies.set('session', session_token)

    # Verify session works
    r = test_client.get('/panel', follow_redirects=False)
    assert r.status_code == 200

    # Logout (increments session_version)
    csrf = signer.dumps(f"csrf:{user['id']}")
    test_client.post('/auth/logout', data={'_csrf': csrf}, follow_redirects=False)

    # Re-set old cookie (simulating attacker reusing stolen cookie)
    test_client.cookies.set('session', session_token)
    r = test_client.get('/panel', follow_redirects=False)
    assert r.status_code == 302  # Redirected to login — old session invalid


# ══════════════════════════════════════════════════════
# CSS upload — additional dangerous patterns
# ══════════════════════════════════════════════════════

def test_panel_brand_upload_url_in_css(session_client):
    """CSS containing url() is rejected (prevents data URI attacks)."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('evil.css', b'body { background: url("data:image/svg+xml,<svg onload>"); }', 'text/css')},
    )
    assert r.status_code == 400


def test_panel_brand_upload_backslash_in_css(session_client):
    """CSS containing backslash (unicode escape bypass) is rejected."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/upload',
        data={'_csrf': csrf},
        files={'file': ('evil.css', b'@\\69mport url("https://evil.com");', 'text/css')},
    )
    assert r.status_code == 400


# ══════════════════════════════════════════════════════
# Token copy — Cache-Control header
# ══════════════════════════════════════════════════════

def test_panel_token_copy_no_cache(session_client):
    """Token copy response has no-store Cache-Control header."""
    client, user, csrf = session_client
    r = client.get('/panel/token/copy')
    assert r.status_code == 200
    assert 'no-store' in r.headers.get('cache-control', '')


# ══════════════════════════════════════════════════════
# Webhook — credit amount validation
# ══════════════════════════════════════════════════════

def test_webhook_negative_credits_rejected(test_client, tmp_db):
    """Negative credit amounts are rejected."""
    tmp_db.create_user('neg@example.com', credits=100)
    r = test_client.post('/webhook/credits',
        json={'email': 'neg@example.com', 'credits': -500, 'reference': 'neg_1'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 400


def test_webhook_zero_credits_rejected(test_client, tmp_db):
    """Zero credit amounts are rejected."""
    tmp_db.create_user('zero@example.com', credits=100)
    r = test_client.post('/webhook/credits',
        json={'email': 'zero@example.com', 'credits': 0, 'reference': 'zero_1'},
        headers={'Authorization': 'Bearer test-webhook-secret'},
    )
    assert r.status_code == 400


# --- Audit #6 fixes ---


@patch('app.render_image', side_effect=Exception("render failed"))
def test_api_generate_credits_refunded_on_failure(mock_render, authed_client, tmp_db):
    """Credits are refunded if rendering fails."""
    client, user = authed_client
    import pytest
    with pytest.raises(Exception, match="render failed"):
        client.post('/api/generate',
            json={'brand': 'example', 'template': 'quote-card', 'size': 'post', 'text': 'X'},
            headers={'Authorization': f'Bearer {user["api_token"]}'},
        )
    # Credits should be refunded
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 100


def test_legacy_session_cookie_rejected(test_client, tmp_db):
    """Old-format session cookies (without version) are rejected."""
    user = tmp_db.create_user('legacy@example.com', credits=100)
    from itsdangerous import URLSafeTimedSerializer
    signer = URLSafeTimedSerializer('test-secret-key')
    # Old format: just user_id, no :version
    token = signer.dumps(user['id'])
    test_client.cookies.set('session', token)
    r = test_client.get('/panel', follow_redirects=False)
    assert r.status_code == 302
    assert '/auth/login' in r.headers['location']


def test_login_email_with_newline_rejected(test_client):
    """Email with newline (SMTP header injection) is rejected."""
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login',
        data={'email': 'user@example.com\nBcc: attacker@evil.com', '_csrf': csrf})
    assert r.status_code == 200
    assert 'invalid' in r.text.lower() or 'Invalid' in r.text


def test_login_email_without_tld_rejected(test_client):
    """Email without TLD is rejected."""
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login', data={'email': 'user@localhost', '_csrf': csrf})
    assert r.status_code == 200
    assert 'invalid' in r.text.lower() or 'Invalid' in r.text


def test_brand_builder_display_name_css_breakout(session_client, tmp_db):
    """CSS breakout characters in display_name are stripped."""
    client, user, csrf = session_client
    r = client.post('/panel/brands/builder',
        data={
            '_csrf': csrf,
            'brand_name': 'safe-brand',
            'display_name': ';} body{display:none} :root{--x:',
            'tagline': 'Normal tagline',
            'theme': 'dark',
            'bg_primary': '#111111',
            'bg_secondary': '#222222',
            'accent': '#00FF00',
            'cta': '#FF0000',
            'cta_text': '#FFFFFF',
            'text_primary': '#EEEEEE',
            'text_secondary': '#AAAAAA',
            'text_muted': '#666666',
            'font_heading': 'Inter',
            'font_body': 'Inter',
            'heading_weight': '700',
            'heading_weight_heavy': '800',
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    # Read the generated CSS and verify no CSS breakout in brand-name value
    import app as app_module
    css_path = app_module.USER_BRANDS_DIR / user['id'] / 'safe-brand.css'
    css_content = css_path.read_text()
    # Extract the --brand-name line and verify dangerous chars are stripped
    for line in css_content.splitlines():
        if '--brand-name' in line:
            assert ';' not in line.split('--brand-name')[1].rstrip(';')
            assert '{' not in line
            assert '}' not in line
            break


# --- Playwright SSRF prevention ---


def test_playwright_route_filter_blocks_internal():
    """Playwright route filter blocks non-file, non-font URLs."""
    from engine import _route_filter, _ALLOWED_NETWORK_HOSTS

    class MockRoute:
        def __init__(self, url):
            self.request = type('R', (), {'url': url})()
            self.continued = False
            self.aborted = False
        def continue_(self): self.continued = True
        def abort(self): self.aborted = True

    # file:// should pass
    r = MockRoute('file:///app/templates/quote-card.html')
    _route_filter(r)
    assert r.continued

    # Google Fonts should pass
    r = MockRoute('https://fonts.googleapis.com/css2?family=Inter')
    _route_filter(r)
    assert r.continued

    r = MockRoute('https://fonts.gstatic.com/s/inter/v18/font.woff2')
    _route_filter(r)
    assert r.continued

    # Internal URLs should be blocked
    r = MockRoute('http://127.0.0.1/admin')
    _route_filter(r)
    assert r.aborted

    r = MockRoute('http://169.254.169.254/latest/meta-data/')
    _route_filter(r)
    assert r.aborted

    r = MockRoute('https://evil.com/steal-data')
    _route_filter(r)
    assert r.aborted


# --- Turnstile CAPTCHA ---


def test_turnstile_disabled_by_default(test_client):
    """Login works without CAPTCHA when Turnstile is not configured."""
    import app as app_module
    assert not app_module.TURNSTILE_ENABLED
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login', data={'email': 'test@example.com', '_csrf': csrf})
    assert r.status_code == 200


def test_turnstile_required_when_configured(test_client, monkeypatch):
    """Login rejected without CAPTCHA token when Turnstile is configured."""
    import importlib
    monkeypatch.setenv('TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setenv('TURNSTILE_SECRET_KEY', 'test-secret-key')
    import app as app_module
    monkeypatch.setattr(app_module, 'TURNSTILE_ENABLED', True)
    monkeypatch.setattr(app_module, 'TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setattr(app_module, 'TURNSTILE_SECRET_KEY', 'test-secret-key')
    csrf = _get_login_csrf(test_client)
    r = test_client.post('/auth/login',
        data={'email': 'test@example.com', '_csrf': csrf},
    )
    assert r.status_code == 400


def test_login_page_shows_turnstile_widget(test_client, monkeypatch):
    """Login page includes Turnstile widget when configured."""
    import app as app_module
    monkeypatch.setattr(app_module, 'TURNSTILE_SITE_KEY', 'test-site-key')
    monkeypatch.setattr(app_module, 'TURNSTILE_ENABLED', True)
    r = test_client.get('/auth/login')
    assert 'cf-turnstile' in r.text
    assert 'test-site-key' in r.text
    assert 'challenges.cloudflare.com' in r.text


# --- Checklist cross-reference fixes ---


def test_api_credits_cache_control(authed_client):
    """API /credits response has no-store Cache-Control."""
    client, user = authed_client
    r = client.get('/api/credits', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    assert 'no-store' in r.headers.get('cache-control', '')


def test_api_brands_cache_control(authed_client):
    """API /brands response has no-store Cache-Control."""
    client, user = authed_client
    r = client.get('/api/brands', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    assert 'no-store' in r.headers.get('cache-control', '')


def test_api_templates_cache_control(authed_client):
    """API /templates response has no-store Cache-Control."""
    client, user = authed_client
    r = client.get('/api/templates', headers={'Authorization': f'Bearer {user["api_token"]}'})
    assert r.status_code == 200
    assert 'no-store' in r.headers.get('cache-control', '')


def test_failed_api_auth_logged(test_client, caplog):
    """Failed Bearer token auth produces a log warning."""
    import logging
    with caplog.at_level(logging.WARNING, logger='app'):
        test_client.get('/api/credits', headers={'Authorization': 'Bearer bad-token'})
    assert any('API auth failed' in msg for msg in caplog.messages)


def test_failed_magic_link_logged(test_client, caplog):
    """Failed magic link verify produces a log warning."""
    import logging
    with caplog.at_level(logging.WARNING, logger='app'):
        test_client.get('/auth/verify?token=bogus-token')
    assert any('Magic link verify failed' in msg for msg in caplog.messages)


def test_failed_webhook_auth_logged(test_client, caplog):
    """Failed webhook auth produces a log warning."""
    import logging
    with caplog.at_level(logging.WARNING, logger='app'):
        test_client.post('/webhook/credits', json={'email': 'x@y.com', 'credits': 100})
    assert any('Webhook auth failed' in msg for msg in caplog.messages)
