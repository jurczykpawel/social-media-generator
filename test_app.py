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
    client, user = session_client
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


def test_login_submit_sends_magic_link(test_client, tmp_db):
    r = test_client.post('/auth/login', data={'email': 'new@example.com'})
    assert r.status_code == 200
    assert 'Check' in r.text or 'Dev mode' in r.text or 'console' in r.text.lower()


def test_login_invalid_email(test_client):
    r = test_client.post('/auth/login', data={'email': 'not-an-email'})
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
    client, user = session_client
    r = client.post('/auth/logout', follow_redirects=False)
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
    client, user = session_client
    r = client.get('/panel')
    assert r.status_code == 200
    assert user['api_token'] in r.text or 'Dashboard' in r.text


def test_panel_brands_page(session_client):
    client, user = session_client
    r = client.get('/panel/brands')
    assert r.status_code == 200
    assert 'example' in r.text.lower()


def test_panel_brand_builder_page(session_client):
    client, user = session_client
    r = client.get('/panel/brands/builder')
    assert r.status_code == 200


def test_panel_brand_builder_save(session_client, tmp_db):
    client, user = session_client
    r = client.post('/panel/brands/builder',
        data={
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
    client, user = session_client
    css_content = b':root { --brand-accent: blue; }'
    r = client.post('/panel/brands/upload',
        files={'file': ('uploaded.css', css_content, 'text/css')},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_panel_brand_upload_non_css(session_client):
    client, user = session_client
    r = client.post('/panel/brands/upload',
        files={'file': ('hack.js', b'alert(1)', 'application/javascript')},
    )
    assert r.status_code == 400


def test_panel_token_regenerate(session_client, tmp_db):
    client, user = session_client
    old_token = user['api_token']
    r = client.post('/panel/token/regenerate', follow_redirects=False)
    assert r.status_code == 302
    updated = tmp_db.get_user(user['id'])
    assert updated['api_token'] != old_token


# ══════════════════════════════════════════════════════
# Preview routes
# ══════════════════════════════════════════════════════

def test_preview_template_css(test_client):
    r = test_client.get('/preview/template/_base.css')
    assert r.status_code == 200
    assert 'text/css' in r.headers['content-type']


def test_preview_template_js(test_client):
    r = test_client.get('/preview/template/_base.js')
    assert r.status_code == 200
    assert 'javascript' in r.headers['content-type']


def test_preview_template_html(test_client):
    r = test_client.get('/preview/template/quote-card')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']


def test_preview_template_not_found(test_client):
    r = test_client.get('/preview/template/nonexistent')
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
    client, user = session_client
    r = client.get('/panel/downloads/ai-instructions')
    assert r.status_code == 200


def test_download_claude_skill(session_client):
    client, user = session_client
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


def test_webhook_hmac_signature(test_client, tmp_db):
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


def test_webhook_bad_hmac(test_client):
    payload = json.dumps({'email': 'x@y.com', 'credits': 100})
    r = test_client.post('/webhook/credits',
        content=payload,
        headers={
            'Content-Type': 'application/json',
            'X-Webhook-Signature': 'deadbeef',
        },
    )
    assert r.status_code == 401


def test_webhook_gateflow_format(test_client, tmp_db):
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


# ══════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════

def test_hex_to_rgba():
    from app import _hex_to_rgba
    assert _hex_to_rgba('#FF0000', 0.5) == 'rgba(255, 0, 0, 0.5)'
    assert _hex_to_rgba('#00FF00', 1.0) == 'rgba(0, 255, 0, 1.0)'
    assert _hex_to_rgba('2DD4BF', 0.12) == 'rgba(45, 212, 191, 0.12)'
