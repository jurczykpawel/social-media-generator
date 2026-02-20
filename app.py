"""
Social Media Graphics Generator — API + Panel
FastAPI app serving both the JSON API (Bearer token) and user panel (session cookie).
"""

import io
import os
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import (
    HTMLResponse, RedirectResponse, Response, StreamingResponse, FileResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature
from pydantic import BaseModel

import db
import mailer
from engine import (
    SIZES, CONTENT_KEYS, META_KEYS, DEFAULT_BRANDS_DIR, TEMPLATES_DIR,
    parse_size, validate_brand, validate_template, list_templates, list_brands,
    render_image,
)

# --- Config ---

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = SCRIPT_DIR / 'data'
USER_BRANDS_DIR = DATA_DIR / 'user_brands'
DOCS_DIR = SCRIPT_DIR / 'docs'

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'login@localhost')
CREDITS_PER_PURCHASE = 100

# Product-to-credits mapping (JSON string in env)
# Example: {"100-credits": 100, "500-credits": 500, "pro-plan": 1000}
import json as _json
_products_raw = os.environ.get('CREDIT_PRODUCTS', '{}')
try:
    CREDIT_PRODUCTS: dict[str, int] = _json.loads(_products_raw)
except _json.JSONDecodeError:
    CREDIT_PRODUCTS = {}

signer = URLSafeTimedSerializer(SECRET_KEY)

# --- App ---

app = FastAPI(title="Social Media Graphics Generator", docs_url="/api/docs")

app.mount("/static", StaticFiles(directory=SCRIPT_DIR / "static"), name="static")
panel_templates = Jinja2Templates(directory=SCRIPT_DIR / "panel")


@app.on_event("startup")
def startup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    (SCRIPT_DIR / "static").mkdir(exist_ok=True)
    db.init_db()


# ============================================================
# Auth helpers
# ============================================================

def get_api_user(request: Request) -> dict:
    """Extract user from Bearer token (for API routes)."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = auth[7:]
    user = db.get_user_by_token(token)
    if not user:
        raise HTTPException(401, "Invalid API token")
    return user


def get_session_user(request: Request) -> dict | None:
    """Extract user from session cookie (for panel routes). Returns None if not logged in."""
    session = request.cookies.get("session")
    if not session:
        return None
    try:
        user_id = signer.loads(session, max_age=30 * 24 * 3600)  # 30 days
    except BadSignature:
        return None
    return db.get_user_by_id(user_id)


def require_session(request: Request) -> dict:
    """Like get_session_user but redirects to login if not authenticated."""
    user = get_session_user(request)
    if not user:
        raise HTTPException(302, headers={"Location": "/auth/login"})
    return user


def set_session_cookie(response: Response, user_id: str):
    token = signer.dumps(user_id)
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)


def resolve_brand_path(brand: str, user_id: str | None = None) -> Path:
    """Find brand CSS: user brands first, then built-in."""
    if user_id:
        user_path = USER_BRANDS_DIR / user_id / f'{brand}.css'
        if user_path.exists():
            return user_path
    builtin_path = DEFAULT_BRANDS_DIR / f'{brand}.css'
    if builtin_path.exists():
        return builtin_path
    raise FileNotFoundError(f"Brand '{brand}' not found")


def get_user_brands_dir(user_id: str) -> Path:
    d = USER_BRANDS_DIR / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ============================================================
# Auth routes
# ============================================================

@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = get_session_user(request)
    if user:
        return RedirectResponse("/panel", status_code=302)
    return panel_templates.TemplateResponse("login.html", {
        "request": request, "message": None, "error": None,
    })


@app.post("/auth/login", response_class=HTMLResponse)
async def login_submit(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    if not email or '@' not in email:
        return panel_templates.TemplateResponse("login.html", {
            "request": request, "message": None, "error": "Invalid email address.",
        })

    token = db.create_magic_link(email)
    link = f"{BASE_URL}/auth/verify?token={token}"

    # Send email (provider auto-detected: AWS SES > Resend > console)
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
        return panel_templates.TemplateResponse("login.html", {
            "request": request, "message": None,
            "error": f"Failed to send email: {e}",
        })

    return panel_templates.TemplateResponse("login.html", {
        "request": request, "error": None,
        "message": "Check your email for the login link." if mailer.is_configured()
                   else "Dev mode — check console for magic link.",
    })


@app.get("/auth/verify")
async def verify_magic_link(token: str):
    email = db.verify_magic_link(token)
    if not email:
        raise HTTPException(400, "Invalid or expired magic link")

    # Find or create user
    user = db.get_user_by_email(email)
    if not user:
        user = db.create_user(email, credits=10)  # 10 free credits for new users
    db.update_last_login(user['id'])

    response = RedirectResponse("/panel", status_code=302)
    set_session_cookie(response, user['id'])
    return response


@app.post("/auth/logout")
async def logout():
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("session")
    return response


# ============================================================
# API routes (Bearer token auth)
# ============================================================

class GenerateRequest(BaseModel):
    brand: str
    template: str
    size: str = "post"
    # Content params — all optional
    text: Optional[str] = None
    attr: Optional[str] = None
    title: Optional[str] = None
    badge: Optional[str] = None
    bullets: Optional[str] = None
    number: Optional[str] = None
    label: Optional[str] = None
    date: Optional[str] = None
    cta: Optional[str] = None
    num: Optional[str] = None
    urgency: Optional[str] = None
    bg_opacity: Optional[str] = None


@app.post("/api/generate")
def api_generate(req: GenerateRequest, request: Request):
    user = get_api_user(request)

    # Validate template
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

    # Check credits
    cost = len(sizes)
    if user['credits'] < cost:
        raise HTTPException(402, f"Insufficient credits. Need {cost}, have {user['credits']}.")

    # Build content params
    params = {}
    for key in CONTENT_KEYS:
        val = getattr(req, key, None)
        if val is not None:
            params[key] = val

    # Generate
    images = []
    for size_name, width, height in sizes:
        png_bytes = render_image(brand_path, req.template, width, height, params)
        images.append((f"{req.brand}_{req.template}_{size_name}_{width}x{height}.png", png_bytes))

    # Deduct credits
    if not db.deduct_credits(user['id'], cost, f"generate:{req.template}"):
        raise HTTPException(402, "Insufficient credits")

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


@app.get("/api/templates")
async def api_templates(request: Request):
    get_api_user(request)
    return {"templates": list_templates()}


@app.get("/api/brands")
async def api_brands(request: Request):
    user = get_api_user(request)
    user_brands = list_brands(get_user_brands_dir(user['id']))
    builtin = list_brands(DEFAULT_BRANDS_DIR)
    return {"user_brands": user_brands, "builtin_brands": builtin}


@app.get("/api/credits")
async def api_credits(request: Request):
    user = get_api_user(request)
    return {"credits": user['credits']}


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
    return panel_templates.TemplateResponse("dashboard.html", {
        "request": request, "user": user, "log": log,
    })


@app.get("/panel/brands", response_class=HTMLResponse)
async def panel_brands(request: Request):
    user = require_session(request)
    user_brands = list_brands(get_user_brands_dir(user['id']))
    builtin = list_brands(DEFAULT_BRANDS_DIR)
    return panel_templates.TemplateResponse("brands.html", {
        "request": request, "user": user,
        "user_brands": user_brands, "builtin_brands": builtin,
    })


@app.post("/panel/brands/upload")
async def panel_brand_upload(request: Request, file: UploadFile = File(...)):
    user = require_session(request)
    if not file.filename.endswith('.css'):
        raise HTTPException(400, "Only .css files allowed")

    content = await file.read()
    if len(content) > 50_000:
        raise HTTPException(400, "File too large (max 50KB)")

    brand_name = file.filename.rsplit('.', 1)[0]
    dest = get_user_brands_dir(user['id']) / f'{brand_name}.css'
    dest.write_bytes(content)

    return RedirectResponse("/panel/brands", status_code=302)


@app.get("/panel/brands/builder", response_class=HTMLResponse)
async def panel_brand_builder(request: Request):
    user = require_session(request)
    return panel_templates.TemplateResponse("brand_builder.html", {
        "request": request, "user": user,
    })


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
    brand_name = brand_name.strip().lower().replace(' ', '-')
    if not brand_name:
        raise HTTPException(400, "Brand name is required")

    display = display_name or brand_name
    tag = tagline or f"// {brand_name}"

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

    dest = get_user_brands_dir(user['id']) / f'{brand_name}.css'
    dest.write_text(css)

    return RedirectResponse("/panel/brands", status_code=302)


@app.get("/panel/brands/{name}/preview", response_class=HTMLResponse)
async def panel_brand_preview(name: str, request: Request):
    user = require_session(request)
    # Verify brand exists (user or built-in)
    user_path = get_user_brands_dir(user['id']) / f'{name}.css'
    if not user_path.exists() and not (DEFAULT_BRANDS_DIR / f'{name}.css').exists():
        raise HTTPException(404, f"Brand '{name}' not found")

    return panel_templates.TemplateResponse("preview.html", {
        "request": request, "user": user,
        "brand_name": name,
        "templates": list_templates(),
    })


@app.get("/panel/brands/{name}/delete")
async def panel_brand_delete(name: str, request: Request):
    user = require_session(request)
    path = get_user_brands_dir(user['id']) / f'{name}.css'
    if path.exists():
        path.unlink()
    return RedirectResponse("/panel/brands", status_code=302)


@app.post("/panel/token/regenerate")
async def panel_token_regenerate(request: Request):
    user = require_session(request)
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
    """Verify webhook authenticity. Supports Bearer token or HMAC signature."""
    import hashlib
    import hmac

    # Option 1: HMAC signature (GateFlow, Stripe-style)
    hmac_secret = os.environ.get("WEBHOOK_HMAC_SECRET", "")
    signature = request.headers.get("X-Webhook-Signature", "") or \
                request.headers.get("X-GateFlow-Signature", "")
    if hmac_secret and signature:
        expected = hmac.new(hmac_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(401, "Invalid HMAC signature")
        return

    # Option 2: Bearer token
    bearer_secret = os.environ.get("WEBHOOK_SECRET", "")
    auth = request.headers.get("Authorization", "")
    if bearer_secret and auth == f"Bearer {bearer_secret}":
        return

    raise HTTPException(401, "Unauthorized webhook")


def _resolve_credits(data: dict) -> int:
    """Resolve credit amount from explicit value or product mapping."""
    # Explicit credits
    if "credits" in data and data["credits"]:
        return int(data["credits"])

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
    reference = data.get("reference", "webhook")

    db.add_credits(user['id'], credits, reference)
    new_balance = user['credits'] + credits
    return {"ok": True, "email": user['email'], "credits_added": credits, "new_balance": new_balance}


# ============================================================
# Preview (iframe-based, no Playwright)
# ============================================================

@app.get("/preview/template/{filename}")
async def preview_template(filename: str, request: Request):
    """Serve template HTML/CSS/JS for iframe preview."""
    # Serve _base.css, _base.js, or template HTML
    if filename.endswith('.css') or filename.endswith('.js'):
        path = TEMPLATES_DIR / filename
    else:
        path = TEMPLATES_DIR / f'{filename}.html'
    if not path.exists():
        raise HTTPException(404, "Template file not found")
    media_types = {'.css': 'text/css', '.js': 'application/javascript', '.html': 'text/html'}
    mt = media_types.get(path.suffix, 'application/octet-stream')
    return FileResponse(path, media_type=mt)


@app.get("/preview/brands/{brand_file}")
async def preview_brand_css(brand_file: str, request: Request):
    """Serve brand CSS for iframe preview (user brands + built-in)."""
    user = get_session_user(request)
    name = brand_file.removesuffix('.css')
    # Check user brands first, then built-in
    if user:
        user_path = get_user_brands_dir(user['id']) / f'{name}.css'
        if user_path.exists():
            return FileResponse(user_path, media_type='text/css')
    builtin_path = DEFAULT_BRANDS_DIR / f'{name}.css'
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
