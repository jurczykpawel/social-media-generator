"""Shared test fixtures."""

import os
import tempfile
from pathlib import Path

import pytest

# Force SQLite for tests (in-memory or temp file)
os.environ['DATABASE_URL'] = ''
os.environ['SECRET_KEY'] = 'test-secret-key'
os.environ['BASE_URL'] = 'http://localhost:8000'
os.environ['SMTP_HOST'] = ''
os.environ['WEBHOOK_SECRET'] = 'test-webhook-secret'
os.environ['WEBHOOK_HMAC_SECRET'] = 'test-hmac-secret'
os.environ['CREDIT_PRODUCTS'] = '{"100-credits": 100, "500-credits": 500}'


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Fresh SQLite database for each test."""
    db_path = tmp_path / 'test.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{db_path}')

    import importlib
    import db
    importlib.reload(db)
    db.init_db()
    yield db
    importlib.reload(db)


@pytest.fixture
def test_user(tmp_db):
    """Create a test user with 100 credits."""
    user = tmp_db.create_user('test@example.com', credits=100)
    return user


@pytest.fixture
def test_client(tmp_db, monkeypatch):
    """FastAPI test client with fresh database."""
    # Patch db module in app to use our test db
    import importlib
    import db
    importlib.reload(db)
    db.init_db()

    import app as app_module
    importlib.reload(app_module)

    from fastapi.testclient import TestClient
    client = TestClient(app_module.app)
    yield client


@pytest.fixture
def authed_client(test_client, tmp_db):
    """Test client + a user with 100 credits. Returns (client, user)."""
    user = tmp_db.create_user('authed@example.com', credits=100)
    return test_client, user


@pytest.fixture
def session_client(test_client, tmp_db):
    """Test client with an active session cookie. Returns (client, user)."""
    user = tmp_db.create_user('session@example.com', credits=100)
    from itsdangerous import URLSafeTimedSerializer
    signer = URLSafeTimedSerializer('test-secret-key')
    token = signer.dumps(user['id'])
    test_client.cookies.set('session', token)
    return test_client, user


@pytest.fixture
def brands_dir(tmp_path):
    """Temporary brands directory with a test brand."""
    d = tmp_path / 'brands'
    d.mkdir()
    (d / 'testbrand.css').write_text(':root { --brand-accent: #ff0000; }')
    return d
