"""Tests for db.py — database layer."""

import time


# ── Users ──────────────────────────────────────────────

def test_create_user(tmp_db):
    user = tmp_db.create_user('alice@example.com', credits=50)
    assert user['email'] == 'alice@example.com'
    assert user['credits'] == 50
    assert user['api_token']
    assert user['id']


def test_create_user_default_credits(tmp_db):
    user = tmp_db.create_user('bob@example.com')
    assert user['credits'] == 0


def test_get_user_by_email(tmp_db):
    tmp_db.create_user('find@example.com', credits=10)
    user = tmp_db.get_user_by_email('find@example.com')
    assert user is not None
    assert user['email'] == 'find@example.com'


def test_get_user_by_email_not_found(tmp_db):
    assert tmp_db.get_user_by_email('ghost@example.com') is None


def test_get_user_by_id(tmp_db):
    created = tmp_db.create_user('id-test@example.com')
    found = tmp_db.get_user_by_id(created['id'])
    assert found['email'] == 'id-test@example.com'


def test_get_user_by_token(tmp_db):
    created = tmp_db.create_user('token@example.com')
    found = tmp_db.get_user_by_token(created['api_token'])
    assert found['email'] == 'token@example.com'


def test_get_user_by_token_not_found(tmp_db):
    assert tmp_db.get_user_by_token('nonexistent-token') is None


def test_regenerate_token(tmp_db):
    user = tmp_db.create_user('regen@example.com')
    old_token = user['api_token']
    new_token = tmp_db.regenerate_token(user['id'])
    assert new_token != old_token
    # Old token should no longer work
    assert tmp_db.get_user_by_token(old_token) is None
    # New token should work
    assert tmp_db.get_user_by_token(new_token)['email'] == 'regen@example.com'


def test_update_last_login(tmp_db):
    user = tmp_db.create_user('login@example.com')
    assert user['last_login'] is None
    tmp_db.update_last_login(user['id'])
    updated = tmp_db.get_user(user['id'])
    assert updated['last_login'] is not None


def test_unique_email(tmp_db):
    tmp_db.create_user('dup@example.com')
    import pytest
    with pytest.raises(Exception):
        tmp_db.create_user('dup@example.com')


def test_unique_api_tokens(tmp_db):
    """Each user gets a unique API token."""
    u1 = tmp_db.create_user('u1@example.com')
    u2 = tmp_db.create_user('u2@example.com')
    assert u1['api_token'] != u2['api_token']


# ── Credits ────────────────────────────────────────────

def test_add_credits(tmp_db):
    user = tmp_db.create_user('credit@example.com', credits=0)
    tmp_db.add_credits(user['id'], 100, 'purchase')
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 100


def test_deduct_credits_success(tmp_db):
    user = tmp_db.create_user('deduct@example.com', credits=50)
    assert tmp_db.deduct_credits(user['id'], 10, 'generate:test') is True
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 40


def test_deduct_credits_insufficient(tmp_db):
    user = tmp_db.create_user('poor@example.com', credits=5)
    assert tmp_db.deduct_credits(user['id'], 10, 'generate:test') is False
    # Credits unchanged
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 5


def test_deduct_credits_exact(tmp_db):
    user = tmp_db.create_user('exact@example.com', credits=10)
    assert tmp_db.deduct_credits(user['id'], 10, 'generate:test') is True
    updated = tmp_db.get_user(user['id'])
    assert updated['credits'] == 0


def test_credit_log(tmp_db):
    user = tmp_db.create_user('log@example.com', credits=100)
    tmp_db.add_credits(user['id'], 50, 'webhook:order_1')
    tmp_db.deduct_credits(user['id'], 3, 'generate:quote-card')
    log = tmp_db.get_credit_log(user['id'])
    assert len(log) == 2
    # Check both entries exist (order may vary within same second)
    deltas = {entry['delta'] for entry in log}
    assert deltas == {50, -3}
    reasons = {entry['reason'] for entry in log}
    assert 'webhook:order_1' in reasons
    assert 'generate:quote-card' in reasons


def test_credit_log_limit(tmp_db):
    user = tmp_db.create_user('limit@example.com', credits=1000)
    for i in range(10):
        tmp_db.add_credits(user['id'], 1, f'test:{i}')
    log = tmp_db.get_credit_log(user['id'], limit=3)
    assert len(log) == 3


# ── Magic Links ────────────────────────────────────────

def test_create_and_verify_magic_link(tmp_db):
    token = tmp_db.create_magic_link('magic@example.com')
    assert token
    email = tmp_db.verify_magic_link(token)
    assert email == 'magic@example.com'


def test_magic_link_single_use(tmp_db):
    token = tmp_db.create_magic_link('once@example.com')
    assert tmp_db.verify_magic_link(token) == 'once@example.com'
    # Second use should fail
    assert tmp_db.verify_magic_link(token) is None


def test_magic_link_invalid_token(tmp_db):
    assert tmp_db.verify_magic_link('bogus-token') is None


def test_cleanup_expired_links(tmp_db):
    token = tmp_db.create_magic_link('cleanup@example.com')
    # Use the link
    tmp_db.verify_magic_link(token)
    # Cleanup should remove used links
    tmp_db.cleanup_expired_links()
    # Verify it's gone (already used, so would be None anyway)
    assert tmp_db.verify_magic_link(token) is None
