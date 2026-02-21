"""
Social Media Graphics Generator — API + Panel
FastAPI app serving both the JSON API (Bearer token) and user panel (session cookie).
"""

import io
import os
import re
import secrets
import time
import threading
import hashlib
import hmac as _hmac
import logging
import uuid
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse, FileResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

import db
import mailer
from engine import (
    SIZES, CONTENT_KEYS, META_KEYS, DEFAULT_BRANDS_DIR, TEMPLATES_DIR,
    parse_size, validate_brand, validate_template, list_templates, list_brands,
    render_image,
)

logger = logging.getLogger(__name__)

# --- Config ---

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / 'data'
USER_BRANDS_DIR = DATA_DIR / 'user_brands'
DOCS_DIR = SCRIPT_DIR / 'docs'

SECRET_KEY = os.environ.get('SECRET_KEY', '')
if not SECRET_KEY:
    SECRET_KEY = 'dev-secret-change-me'
    logger.warning("SECRET_KEY not set — using insecure default. Set SECRET_KEY env var in production!")

# Fail-fast in production
if os.environ.get('BASE_URL', '').startswith('https://') and SECRET_KEY == 'dev-secret-change-me':
    raise RuntimeError("SECRET_KEY must be set in production! Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")

_CSS_DANGEROUS_PATTERNS = [
    '<script', 'javascript:', '@import', 'expression(', '-moz-binding', 'behavior:',
    'url(', 'data:', '@charset', '\\',
]

BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'login@localhost')
CREDITS_PER_PURCHASE = 100
IS_PRODUCTION = BASE_URL.startswith('https://')

# Product-to-credits mapping (JSON string in env)
import json as _json
_products_raw = os.environ.get('CREDIT_PRODUCTS', '{}')
try:
    CREDIT_PRODUCTS: dict[str, int] = _json.loads(_products_raw)
except _json.JSONDecodeError:
    CREDIT_PRODUCTS = {}

signer = URLSafeTimedSerializer(SECRET_KEY)

# --- Turnstile CAPTCHA (optional) ---
TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)


async def _verify_turnstile(request: Request):
    """Verify Cloudflare Turnstile token. No-op if not configured."""
    if not TURNSTILE_ENABLED:
        return
    form = await request.form()
    token = form.get('cf-turnstile-response', '')
    if not token:
        raise HTTPException(400, "CAPTCHA verification required")
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post('https://challenges.cloudflare.com/turnstile/v0/siteverify', data={
            'secret': TURNSTILE_SECRET_KEY,
            'response': token,
            'remoteip': request.client.host if request.client else '',
        })
    result = resp.json()
    if not result.get('success'):
        raise HTTPException(400, "CAPTCHA verification failed")


# --- Name validation ---

_SAFE_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')

def _sanitize_name(name: str, label: str = "name") -> str:
    """Validate that a name is safe for use in file paths."""
    name = name.strip().lower()
    if not name or not _SAFE_NAME_RE.match(name) or '..' in name:
        raise HTTPException(400, f"Invalid {label}: only lowercase letters, numbers, hyphens, and underscores allowed")
    if len(name) > 64:
        raise HTTPException(400, f"Invalid {label}: max 64 characters")
    return name


def _safe_resolve(base_dir: Path, filename: str) -> Path:
    """Resolve a path and verify it stays within base_dir."""
    resolved = (base_dir / filename).resolve()
    if not str(resolved).startswith(str(base_dir.resolve())):
        raise HTTPException(400, "Invalid path")
    return resolved

# --- Rate limiting (in-memory, thread-safe) ---

_rate_limits: dict[str, list[float]] = defaultdict(list)
_rate_limits_last_cleanup = time.time()
_rate_limits_lock = threading.Lock()

def _check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """Simple in-memory rate limiter. Raises 429 if exceeded."""
    global _rate_limits_last_cleanup
    now = time.time()
    with _rate_limits_lock:
        # Periodic cleanup of stale keys (every 5 minutes)
        if now - _rate_limits_last_cleanup > 300:
            stale = [k for k, v in _rate_limits.items() if not v or now - v[-1] > 300]
            for k in stale:
                del _rate_limits[k]
            _rate_limits_last_cleanup = now
        timestamps = _rate_limits[key]
        # Remove old entries
        _rate_limits[key] = [t for t in timestamps if now - t < window_seconds]
        if len(_rate_limits[key]) >= max_requests:
            raise HTTPException(429, "Too many requests. Try again later.")
        _rate_limits[key].append(now)

# --- CSRF ---

def _generate_csrf_token(session_id: str) -> str:
    """Generate a CSRF token tied to the session."""
    return signer.dumps(f"csrf:{session_id}")


def _validate_csrf_token(request: Request, user: dict):
    """Validate CSRF token from form data."""
    # API calls (Bearer token) don't need CSRF
    if request.headers.get("Authorization", "").startswith("Bearer"):
        return
    # For form submissions, check the token
    # Token is validated in the route after form data is available


async def _check_csrf(request: Request, user_id: str):
    """Check CSRF token in form submission."""
    form = await request.form()
    token = form.get("_csrf", "")
    if not token:
        raise HTTPException(403, "Missing CSRF token")
    try:
        value = signer.loads(str(token), max_age=3600)  # 1 hour
        if value != f"csrf:{user_id}":
            raise HTTPException(403, "Invalid CSRF token")
    except BadSignature:
        raise HTTPException(403, "Invalid CSRF token")

# --- Security headers middleware ---

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        csp_script = "'self'"
        csp_frame = "'self'"
        if TURNSTILE_ENABLED:
            csp_script += " https://challenges.cloudflare.com"
            csp_frame += " https://challenges.cloudflare.com"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            f"script-src {csp_script}; "
            "img-src 'self' data:; "
            f"frame-src {csp_frame}"
        )
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

# --- App ---

app = FastAPI(
    title="Social Media Graphics Generator",
    docs_url=None if IS_PRODUCTION else "/api/docs",
    redoc_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.mount("/static", StaticFiles(directory=SCRIPT_DIR / "static"), name="static")
panel_templates = Jinja2Templates(directory=SCRIPT_DIR / "panel")


@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "static").mkdir(exist_ok=True)
    db.init_db()
    db.cleanup_expired_links()


# ============================================================
# Auth helpers
# ============================================================

def get_api_user(request: Request) -> dict:
    """Extract user from Bearer token (for API routes)."""
    client_ip = request.client.host if request.client else "unknown"
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        logger.warning("API auth failed: missing Bearer header (ip=%s, path=%s)", client_ip, request.url.path)
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth[7:]
    user = db.get_user_by_token(token)
    if not user:
        logger.warning("API auth failed: invalid token (ip=%s, path=%s)", client_ip, request.url.path)
        raise HTTPException(401, "Invalid API token")
    return user


def get_session_user(request: Request) -> dict | None:
    """Extract user from session cookie (for panel routes). Returns None if not logged in."""
    session = request.cookies.get("session")
    if not session:
        return None
    try:
        payload = signer.loads(session, max_age=30 * 24 * 3600)  # 30 days
    except BadSignature:
        return None
    # Parse "user_id:version" format — reject old cookies without version
    if ':' not in str(payload):
        return None
    user_id, version_str = str(payload).rsplit(':', 1)
    try:
        cookie_version = int(version_str)
    except ValueError:
        return None
    user = db.get_user_by_id(user_id)
    if not user:
        return None
    # Verify session version matches (invalidated cookies have mismatched version)
    if user.get('session_version', 1) != cookie_version:
        return None
    return user


def require_session(request: Request) -> dict:
    """Like get_session_user but redirects to login if not authenticated."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(302, headers={"Location": "/auth/login"})
    return user


def set_session_cookie(response: Response, user_id: str, session_version: int = 1):
    token = signer.dumps(f"{user_id}:{session_version}")
    response.set_cookie(
        "session", token,
        httponly=True,
        samesite="lax",
        secure=IS_PRODUCTION,
        max_age=30 * 24 * 3600,
    )


def resolve_brand_path(brand: str, user_id: str | None = None) -> Path:
    """Find brand CSS: user brands first, then built-in."""
    brand = _sanitize_name(brand, "brand")
    if user_id:
        user_path = _safe_resolve(USER_BRANDS_DIR / user_id, f'{brand}.css')
        if user_path.exists():
            return user_path
    builtin_path = _safe_resolve(DEFAULT_BRANDS_DIR, f'{brand}.css')
    if builtin_path.exists():
        return builtin_path
    raise FileNotFoundError(f"Brand '{brand}' not found")


def get_user_brands_dir(user_id: str) -> Path:
    d = USER_BRANDS_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _csrf_context(request: Request, user: dict, **extra) -> dict:
    """Build template context with CSRF token."""
    csrf_token = _generate_csrf_token(user['id'])
    return {"request": request, "user": user, "csrf_token": csrf_token, **extra}


# ============================================================
# Auth routes
# ============================================================

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_session_user(request)
    if user:
        return RedirectResponse("/panel", status_code=302)
    csrf_token = signer.dumps(f"csrf:anon:{secrets.token_hex(8)}")
    return panel_templates.TemplateResponse("login.html", {
        "request": request, "message": None, "error": None,
        "csrf_token": csrf_token,
        "turnstile_site_key": TURNSTILE_SITE_KEY,
    })


@app.post("/auth/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...)):
    # Rate limit: 5 login attempts per IP per minute
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"login:{client_ip}", max_requests=5, window_seconds=60)

    # Validate CSRF (anonymous token — just check it's a valid signed value)
    form = await request.form()
    csrf = form.get("_csrf", "")
    if not csrf:
        raise HTTPException(403, "Missing CSRF token")
    try:
        value = signer.loads(str(csrf), max_age=3600)
        if not str(value).startswith("csrf:anon:"):
            raise HTTPException(403, "Invalid CSRF token")
    except BadSignature:
        raise HTTPException(403, "Invalid CSRF token")

    # Verify CAPTCHA (if configured)
    await _verify_turnstile(request)

    email = email.strip().lower()
    _EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
    if not email or not _EMAIL_RE.match(email) or len(email) > 254:
        csrf_token = signer.dumps(f"csrf:anon:{secrets.token_hex(8)}")
        return panel_templates.TemplateResponse("login.html", {
            "request": request, "message": None, "error": "Invalid email address.",
            "csrf_token": csrf_token,
            "turnstile_site_key": TURNSTILE_SITE_KEY,
        })

    token = db.create_magic_link(email)
    link = f"{BASE_URL}/auth/verify?token={token}"

    try:
        mailer.send_email(
            to=email,
            subject="Your login link — Social Media Generator",
            html=f"""
                <p>Click to log in:</p>
                <p><a href="{link}" style="font-size:18px;font-weight:bold">{link}</a></p>
                <p>This link expires in 15 minutes.</p>
            """,
        )
    except Exception as e:
        logger.error(f"Failed to send magic link: {e}")
        csrf_token = signer.dumps(f"csrf:anon:{secrets.token_hex(8)}")
        return panel_templates.TemplateResponse("login.html", {
            "request": request, "message": None,
            "error": "Failed to send email. Please try again later.",
            "csrf_token": csrf_token,
            "turnstile_site_key": TURNSTILE_SITE_KEY,
        })

    return panel_templates.TemplateResponse("login.html", {
        "request": request, "error": None,
        "message": "Check your email for the login link." if mailer.is_configured()
                   else "Dev mode — check console for magic link.",
        "csrf_token": "",
        "turnstile_site_key": "",
    })


@app.get("/auth/verify")
async def verify_magic_link(request: Request, token: str):
    # Rate limit: 10 verify attempts per IP per minute
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"verify:{client_ip}", max_requests=10, window_seconds=60)
    email = db.verify_magic_link(token)
    if not email:
        logger.warning("Magic link verify failed: invalid/expired token (ip=%s)", client_ip)
        raise HTTPException(400, "Invalid or expired magic link")

    # Find or create user
    user = db.get_user_by_email(email)
    if not user:
        user = db.create_user(email, credits=10)  # 10 free credits for new users
    db.update_last_login(user['id'])

    response = RedirectResponse("/panel", status_code=302)
    set_session_cookie(response, user['id'], user.get('session_version', 1))
    return response


@app.post("/auth/logout")
async def logout(request: Request):
    user = get_session_user(request)
    if user:
        await _check_csrf(request, user['id'])
        db.increment_session_version(user['id'])
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("session")
    return response


# ============================================================
# API routes (Bearer token auth)
# ============================================================

class GenerateRequest(BaseModel):
    brand: str = Field(max_length=64)
    template: str = Field(max_length=64)
    size: str = Field(default="post", max_length=20)
    # Content params — all optional, max 2000 chars each
    text: Optional[str] = Field(default=None, max_length=2000)
    attr: Optional[str] = Field(default=None, max_length=200)
    title: Optional[str] = Field(default=None, max_length=500)
    badge: Optional[str] = Field(default=None, max_length=100)
    bullets: Optional[str] = Field(default=None, max_length=2000)
    number: Optional[str] = Field(default=None, max_length=50)
    label: Optional[str] = Field(default=None, max_length=200)
    date: Optional[str] = Field(default=None, max_length=100)
    cta: Optional[str] = Field(default=None, max_length=100)
    num: Optional[str] = Field(default=None, max_length=20)
    urgency: Optional[str] = Field(default=None, max_length=200)
    bg_opacity: Optional[str] = Field(default=None, max_length=10)


@app.post("/api/generate")
def api_generate(req: GenerateRequest, request: Request):
    user = get_api_user(request)

    # Rate limit: 30 generations per minute per user
    _check_rate_limit(f"generate:{user['id']}", max_requests=30, window_seconds=60)

    # Validate template name + existence
    _sanitize_name(req.template, "template")
    try:
        validate_template(req.template)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))

    # Resolve brand
    try:
        brand_path = resolve_brand_path(req.brand, user['id'])
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))

    # Parse sizes
    try:
        sizes = parse_size(req.size)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Build content params
    params = {}
    for key in CONTENT_KEYS:
        val = getattr(req, key, None)
        if val is not None:
            params[key] = val

    # Deduct credits BEFORE rendering to prevent resource exhaustion via concurrent requests
    cost = len(sizes)
    if not db.deduct_credits(user['id'], cost, f"generate:{req.template}"):
        raise HTTPException(402, f"Insufficient credits. Need {cost}, have {user['credits']}.")

    # Generate (refund credits on failure)
    try:
        images = []
        for size_name, width, height in sizes:
            png_bytes = render_image(brand_path, req.template, width, height, params)
            images.append((f"{req.brand}_{req.template}_{size_name}_{width}x{height}.png", png_bytes))
    except Exception:
        db.add_credits(user['id'], cost, f"refund:generate:{req.template}")
        raise

    # Return single PNG or ZIP
    if len(images) == 1:
        filename, data = images[0]
        return Response(
            content=data,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Multiple images → ZIP
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, data in images:
            zf.writestr(filename, data)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{req.brand}_{req.template}.zip"'},
    )


_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, private"}


@app.get("/api/templates")
async def api_templates(request: Request):
    get_api_user(request)
    return JSONResponse({"templates": list_templates()}, headers=_NO_CACHE)


@app.get("/api/brands")
async def api_brands(request: Request):
    user = get_api_user(request)
    user_brands = list_brands(get_user_brands_dir(user['id']))
    builtin = list_brands(DEFAULT_BRANDS_DIR)
    return JSONResponse({"user_brands": user_brands, "builtin_brands": builtin}, headers=_NO_CACHE)


@app.get("/api/credits")
async def api_credits(request: Request):
    user = get_api_user(request)
    return JSONResponse({"credits": user['credits']}, headers=_NO_CACHE)


# ============================================================
# Panel routes (session cookie auth)
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = get_session_user(request)
    if user:
        return RedirectResponse("/panel", status_code=302)
    return RedirectResponse("/auth/login", status_code=302)


@app.get("/panel", response_class=HTMLResponse)
async def panel_dashboard(request: Request):
    user = require_session(request)
    log = db.get_credit_log(user['id'], limit=10)
    return panel_templates.TemplateResponse("dashboard.html",
        _csrf_context(request, user, log=log))


@app.get("/panel/brands", response_class=HTMLResponse)
async def panel_brands(request: Request):
    user = require_session(request)
    user_brands = list_brands(get_user_brands_dir(user['id']))
    builtin = list_brands(DEFAULT_BRANDS_DIR)
    return panel_templates.TemplateResponse("brands.html",
        _csrf_context(request, user, user_brands=user_brands, builtin_brands=builtin))


@app.post("/panel/brands/upload")
async def panel_brand_upload(request: Request, file: UploadFile = File(...)):
    user = require_session(request)
    await _check_csrf(request, user['id'])

    if not file.filename or not file.filename.endswith('.css'):
        raise HTTPException(400, "Only .css files allowed")

    content = await file.read()
    if len(content) > 50_000:
        raise HTTPException(400, "File too large (max 50KB)")

    # Validate content looks like CSS
    text = content.decode('utf-8', errors='replace')
    text_lower = text.lower()
    for pattern in _CSS_DANGEROUS_PATTERNS:
        if pattern in text_lower:
            raise HTTPException(400, "Invalid CSS content")

    brand_name = file.filename.rsplit('.', 1)[0]
    brand_name = _sanitize_name(brand_name, "brand name")
    dest = _safe_resolve(get_user_brands_dir(user['id']), f'{brand_name}.css')
    dest.write_bytes(content)

    return RedirectResponse("/panel/brands", status_code=302)


@app.get("/panel/brands/builder", response_class=HTMLResponse)
async def panel_brand_builder(request: Request):
    user = require_session(request)
    return panel_templates.TemplateResponse("brand_builder.html",
        _csrf_context(request, user))


_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
_ALLOWED_FONTS = {
    'Inter', 'Space Grotesk', 'Outfit', 'Poppins', 'Plus Jakarta Sans',
    'DM Sans', 'Lato', 'Montserrat', 'Raleway',
}
_ALLOWED_WEIGHTS = {'400', '500', '600', '700', '800', '900'}


@app.post("/panel/brands/builder")
async def panel_brand_builder_save(
    request: Request,
    brand_name: str = Form(...),
    display_name: str = Form(""),
    tagline: str = Form(""),
    theme: str = Form("dark"),
    bg_primary: str = Form("#0F1117"),
    bg_secondary: str = Form("#151720"),
    accent: str = Form("#2DD4BF"),
    cta: str = Form("#F97316"),
    cta_text: str = Form("#0F1117"),
    text_primary: str = Form("#F1F5F9"),
    text_secondary: str = Form("#94A3B8"),
    text_muted: str = Form("#64748B"),
    font_heading: str = Form("Inter"),
    font_body: str = Form("Inter"),
    heading_weight: str = Form("700"),
    heading_weight_heavy: str = Form("700"),
):
    user = require_session(request)
    await _check_csrf(request, user['id'])

    brand_name = _sanitize_name(brand_name, "brand name")

    # Validate all color inputs
    colors = {
        'bg_primary': bg_primary, 'bg_secondary': bg_secondary,
        'accent': accent, 'cta': cta, 'cta_text': cta_text,
        'text_primary': text_primary, 'text_secondary': text_secondary,
        'text_muted': text_muted,
    }
    for name, value in colors.items():
        if not _HEX_COLOR_RE.match(value):
            raise HTTPException(400, f"Invalid color for {name}: must be #RRGGBB")

    # Validate fonts
    if font_heading not in _ALLOWED_FONTS:
        raise HTTPException(400, f"Invalid heading font")
    if font_body not in _ALLOWED_FONTS:
        raise HTTPException(400, f"Invalid body font")
    if heading_weight not in _ALLOWED_WEIGHTS:
        raise HTTPException(400, f"Invalid heading weight")
    if heading_weight_heavy not in _ALLOWED_WEIGHTS:
        raise HTTPException(400, f"Invalid heading weight")
    if theme not in ('dark', 'light'):
        raise HTTPException(400, "Invalid theme")

    # Sanitize text fields for CSS context — whitelist safe characters
    _SAFE_CSS_STRING_RE = re.compile(r'[^a-zA-Z0-9\s.,!?@#&*()+=/:\-]')
    display = _SAFE_CSS_STRING_RE.sub('', (display_name or brand_name))[:64]
    tag = _SAFE_CSS_STRING_RE.sub('', (tagline or f"// {brand_name}"))[:128]

    # Generate Google Fonts import
    fonts = set(filter(None, [font_heading, font_body]))
    font_import = "https://fonts.googleapis.com/css2?{}&family=JetBrains+Mono:wght@400;500&display=swap".format(
        "&".join(f"family={f.replace(' ', '+')}:wght@400;500;600;700" for f in fonts)
    )

    # Compute derived colors
    accent_dim = _hex_to_rgba(accent, 0.10)
    border_color = "rgba(255, 255, 255, 0.06)" if theme == "dark" else "rgba(0, 0, 0, 0.08)"
    border_accent = _hex_to_rgba(accent, 0.15)

    css = f"""@import url('{font_import}');

:root {{
    --brand-name: "{display}";
    --brand-tagline: "{tag}";

    --brand-bg-primary: {bg_primary};
    --brand-bg-secondary: {bg_secondary};
    --brand-bg-surface: {bg_secondary};
    --brand-bg-card: {bg_secondary};

    --brand-accent: {accent};
    --brand-accent-hover: {accent};
    --brand-accent-dim: {accent_dim};

    --brand-cta: {cta};
    --brand-cta-hover: {cta};
    --brand-cta-text: {cta_text};

    --brand-text-primary: {text_primary};
    --brand-text-secondary: {text_secondary};
    --brand-text-muted: {text_muted};

    --brand-border: {border_color};
    --brand-border-accent: {border_accent};
    --brand-shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.2);
    --brand-shadow-md: 0 4px 16px rgba(0, 0, 0, 0.25);

    --brand-success: #34D399;
    --brand-error: #EF4444;

    --brand-font-heading: '{font_heading}', system-ui, sans-serif;
    --brand-font-body: '{font_body}', system-ui, sans-serif;
    --brand-font-mono: 'JetBrains Mono', monospace;
    --brand-heading-weight: {heading_weight};
    --brand-heading-weight-heavy: {heading_weight_heavy};

    --brand-radius-sm: 6px;
    --brand-radius-md: 10px;
    --brand-radius-lg: 16px;

    --brand-theme: {theme};

    --brand-badge-accent-bg: {_hex_to_rgba(accent, 0.12)};
    --brand-badge-cta-bg: {_hex_to_rgba(cta, 0.12)};
    --brand-badge-success-bg: rgba(52, 211, 153, 0.08);
}}
"""

    dest = _safe_resolve(get_user_brands_dir(user['id']), f'{brand_name}.css')
    dest.write_text(css)

    return RedirectResponse("/panel/brands", status_code=302)


@app.get("/panel/brands/{name}/preview", response_class=HTMLResponse)
async def panel_brand_preview(name: str, request: Request):
    user = require_session(request)
    name = _sanitize_name(name, "brand")
    user_path = _safe_resolve(get_user_brands_dir(user['id']), f'{name}.css')
    if not user_path.exists() and not _safe_resolve(DEFAULT_BRANDS_DIR, f'{name}.css').exists():
        raise HTTPException(404, f"Brand not found")

    return panel_templates.TemplateResponse("preview.html", {
        "request": request, "user": user,
        "brand_name": name,
        "templates": list_templates(),
    })


@app.post("/panel/brands/{name}/delete")
async def panel_brand_delete(name: str, request: Request):
    user = require_session(request)
    await _check_csrf(request, user['id'])
    name = _sanitize_name(name, "brand")
    path = _safe_resolve(get_user_brands_dir(user['id']), f'{name}.css')
    if path.exists():
        path.unlink()
    return RedirectResponse("/panel/brands", status_code=302)


@app.post("/panel/token/regenerate")
async def panel_token_regenerate(request: Request):
    user = require_session(request)
    await _check_csrf(request, user['id'])
    _check_rate_limit(f"token_regen:{user['id']}", max_requests=5, window_seconds=3600)
    db.regenerate_token(user['id'])
    return RedirectResponse("/panel", status_code=302)


# ============================================================
# Downloads
# ============================================================

@app.get("/panel/downloads/ai-instructions")
async def download_ai_instructions(request: Request):
    require_session(request)
    path = DOCS_DIR / "ai-brand-instructions.md"
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename="ai-brand-instructions.md", media_type="text/markdown")


@app.get("/panel/downloads/claude-skill")
async def download_claude_skill(request: Request):
    require_session(request)
    path = DOCS_DIR / "claude-code-skill.md"
    if not path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path, filename="claude-code-skill.md", media_type="text/markdown")


# ============================================================
# Credits webhook (universal — works with any payment provider)
# ============================================================

def _verify_webhook(request: Request, body: bytes) -> None:
    """Verify webhook authenticity. Supports Bearer token or HMAC signature.

    If HMAC secret is configured, signature is required (no fallthrough to Bearer).
    Bearer token is only used when HMAC is not configured.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Option 1: HMAC signature (GateFlow, Stripe-style)
    hmac_secret = os.environ.get("WEBHOOK_HMAC_SECRET", "")
    if hmac_secret:
        # HMAC is configured — require a valid signature (no fallthrough)
        signature = request.headers.get("X-Webhook-Signature", "") or \
                    request.headers.get("X-GateFlow-Signature", "")
        if not signature:
            logger.warning("Webhook auth failed: missing HMAC signature (ip=%s)", client_ip)
            raise HTTPException(401, "Missing webhook signature")
        expected = _hmac.new(hmac_secret.encode(), body, hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(signature, expected):
            logger.warning("Webhook auth failed: invalid HMAC signature (ip=%s)", client_ip)
            raise HTTPException(401, "Invalid HMAC signature")
        return

    # Option 2: Bearer token (only when HMAC not configured)
    bearer_secret = os.environ.get("WEBHOOK_SECRET", "")
    auth = request.headers.get("Authorization", "")
    if bearer_secret and auth.startswith("Bearer ") and \
       _hmac.compare_digest(auth[7:], bearer_secret):
        return

    logger.warning("Webhook auth failed: no valid credentials (ip=%s)", client_ip)
    raise HTTPException(401, "Unauthorized webhook")


def _resolve_credits(data: dict) -> int:
    """Resolve credit amount from explicit value or product mapping."""
    # Explicit credits
    if "credits" in data and data["credits"] is not None:
        credits = int(data["credits"])
        if credits <= 0 or credits > 1_000_000:
            raise HTTPException(400, "Credits must be between 1 and 1000000")
        return credits

    # Product slug/id lookup
    product = data.get("product") or ""
    if isinstance(product, dict):
        product = product.get("slug") or product.get("id") or ""
    if product and product in CREDIT_PRODUCTS:
        return CREDIT_PRODUCTS[product]

    # Default
    if CREDITS_PER_PURCHASE:
        return CREDITS_PER_PURCHASE

    raise HTTPException(400, "Cannot determine credits: set 'credits' or configure CREDIT_PRODUCTS")


def _resolve_user(data: dict) -> dict:
    """Find user by email or user_id. Creates account if email-only and not found."""
    # By user_id
    user_id = data.get("user_id")
    if user_id:
        user = db.get_user(user_id)
        if user:
            return user

    # By email (from top-level or nested customer object)
    email = data.get("email") or ""
    customer = data.get("customer") or data.get("data", {}).get("customer", {})
    if not email and isinstance(customer, dict):
        email = customer.get("email", "")
    email = email.strip().lower()

    if not email:
        raise HTTPException(400, "email or user_id required")

    user = db.get_user_by_email(email)
    if user:
        return user

    # Auto-create user on first purchase
    return db.create_user(email)


@app.post("/webhook/credits")
async def credits_webhook(request: Request):
    """Universal webhook to add credits after purchase.

    Accepts any of these formats:

    Direct:     {"email": "x@y.com", "credits": 100, "reference": "order_123"}
    Product:    {"email": "x@y.com", "product": "100-credits", "reference": "..."}
    GateFlow:   {"event": "purchase.completed", "data": {"customer": {"email": "..."}, "product": {"slug": "..."}, ...}}

    Auth: Bearer token (WEBHOOK_SECRET) or HMAC signature (WEBHOOK_HMAC_SECRET).
    Product-to-credits mapping configured via CREDIT_PRODUCTS env var (JSON).
    """
    # Rate limit: 60 webhook calls per minute
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"webhook:{client_ip}", max_requests=60, window_seconds=60)

    body = await request.body()
    _verify_webhook(request, body)

    raw = await request.json()

    # Normalize GateFlow's nested format to flat
    if "event" in raw and "data" in raw:
        data = raw["data"]
        data["reference"] = data.get("reference", f"{raw['event']}:{raw['data'].get('order', {}).get('sessionId', '')}")
    else:
        data = raw

    user = _resolve_user(data)
    credits = _resolve_credits(data)
    reference = data.get("reference") or f"webhook:{uuid.uuid4()}"

    # Atomic replay protection: check + insert in single transaction
    added = db.add_credits_atomic(user['id'], credits, reference)
    if not added:
        return {"ok": True, "email": user['email'], "credits_added": 0,
                "new_balance": user['credits'], "duplicate": True}

    new_balance = user['credits'] + credits
    return {"ok": True, "email": user['email'], "credits_added": credits, "new_balance": new_balance}


# ============================================================
# Preview (iframe-based, no Playwright)
# ============================================================

_ALLOWED_TEMPLATE_EXTENSIONS = {'.css', '.js', '.html'}

@app.get("/panel/token/copy")
async def panel_token_copy(request: Request):
    """Return full API token via JSON (avoids exposing token in DOM)."""
    user = require_session(request)
    return JSONResponse({"token": user['api_token']}, headers=_NO_CACHE)


@app.get("/preview/template/{filename}")
async def preview_template(filename: str, request: Request):
    """Serve template HTML/CSS/JS for iframe preview."""
    require_session(request)
    # Validate filename: only allow known extensions, no path traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(400, "Invalid filename")

    if filename.endswith('.css') or filename.endswith('.js'):
        path = TEMPLATES_DIR / filename
    else:
        path = TEMPLATES_DIR / f'{filename}.html'

    # Verify resolved path is within templates dir
    resolved = path.resolve()
    if not str(resolved).startswith(str(TEMPLATES_DIR.resolve())):
        raise HTTPException(400, "Invalid path")

    if not resolved.exists():
        raise HTTPException(404, "Template file not found")
    if resolved.suffix not in _ALLOWED_TEMPLATE_EXTENSIONS:
        raise HTTPException(400, "Invalid file type")

    media_types = {'.css': 'text/css', '.js': 'application/javascript', '.html': 'text/html'}
    mt = media_types.get(resolved.suffix, 'application/octet-stream')
    return FileResponse(resolved, media_type=mt)


@app.get("/preview/brands/{brand_file}")
async def preview_brand_css(brand_file: str, request: Request):
    """Serve brand CSS for iframe preview (user brands + built-in)."""
    if '..' in brand_file or '/' in brand_file or '\\' in brand_file:
        raise HTTPException(400, "Invalid filename")

    user = get_session_user(request)
    name = brand_file.removesuffix('.css')
    name = _sanitize_name(name, "brand")

    if user:
        user_path = _safe_resolve(get_user_brands_dir(user['id']), f'{name}.css')
        if user_path.exists():
            return FileResponse(user_path, media_type='text/css')
    builtin_path = _safe_resolve(DEFAULT_BRANDS_DIR, f'{name}.css')
    if builtin_path.exists():
        return FileResponse(builtin_path, media_type='text/css')
    raise HTTPException(404, "Brand not found")


# ============================================================
# Health
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok"}


# ============================================================
# Helpers
# ============================================================

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"
