# Social Media Graphics Generator

**One text, multiple formats.** Generate brand-consistent social media graphics from HTML templates. Instagram posts, Stories, YouTube thumbnails — all pixel-perfect, all on-brand.

HTML templates use CSS custom properties (`--brand-*`) for theming. A Python script renders them via headless Chromium (Playwright) and saves PNGs. No Photoshop, no Canva, no manual resizing.

Works as a **CLI tool**, a **REST API**, or both — with a built-in user panel for brand management.

---

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [API](#api)
- [User Panel](#user-panel)
- [CLI Usage](#cli-usage)
- [Templates](#templates)
- [Sizes](#sizes)
- [Safe Zones](#safe-zones)
- [Create Your Brand](#create-your-brand)
- [Adding Templates](#adding-templates)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [License](#license)

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/jurczykpawel/social-media-generator.git
cd social-media-generator
cp .env.example .env        # edit as needed
docker compose up
```

Open http://localhost:8000 — done.

The default setup includes PostgreSQL. To use SQLite instead, remove the `db` service from `docker-compose.yml` and clear `DATABASE_URL` in `.env`.

### Local (dev)

```bash
git clone https://github.com/jurczykpawel/social-media-generator.git
cd social-media-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# CLI only:
python generate.py --brand example --template quote-card \
    --text "Ship it before it's perfect." --attr "A wise engineer"

# API + panel:
uvicorn app:app
```

---

## How It Works

```
brands/mybrand.css        templates/quote-card.html        engine.py
  --brand-accent: #2DD4BF    color: var(--brand-accent)      Playwright screenshot
  --brand-font: 'Inter'      font: var(--brand-font)            ↓
       ↓                          ↓                         PNG bytes
       └──────────── merge ───────┘                    (returned via API or saved to disk)
```

1. **Brand** = CSS file with `--brand-*` color/font tokens
2. **Template** = HTML file that reads those tokens
3. **Engine** = Playwright opens the template in headless Chromium, sets viewport to target size, takes a screenshot

Same template, same text — three formats from one command.

---

## API

REST API with Bearer token authentication and credit-based usage.

### Generate image

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"brand":"example","template":"quote-card","size":"post","text":"Hello world","attr":"Author"}' \
  -o output.png
```

Returns `image/png` for a single size, `application/zip` (3 PNGs) when `size=all`.

**Cost:** 1 credit per image (`size=all` = 3 credits).

### Other endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/generate` | Generate image(s) |
| `GET` | `/api/templates` | List available templates |
| `GET` | `/api/brands` | List user's brands |
| `GET` | `/api/credits` | Check credit balance |
| `GET` | `/health` | Health check |

### Webhook (credit fulfillment)

External payment provider calls this to add credits after purchase:

```bash
curl -X POST http://localhost:8000/webhook/credits \
  -H "Authorization: Bearer WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"...","credits":100,"reference":"order_123"}'
```

Set `WEBHOOK_SECRET` in `.env` to protect this endpoint.

---

## User Panel

Server-rendered HTML panel at `/panel` with:

- **Magic link login** — email-based, no passwords
- **Dashboard** — credit balance, API token (copy/regenerate), curl example, downloads
- **Brand management** — upload CSS or build visually with the Brand Builder
- **Brand Builder** — color pickers, font selectors, dark/light theme, live preview
- **Brand preview** — see all templates rendered with your brand (iframe-based, instant)
- **Downloads** — AI brand instructions (for ChatGPT/Claude) + Claude Code skill

### Auth flow

1. User enters email at `/auth/login`
2. Magic link sent via SMTP (or printed to console in dev mode)
3. Click link → session cookie → redirected to `/panel`

---

## CLI Usage

The CLI works independently of the API — no server, no database, no auth needed.

### From JSON (recommended)

```json
{
    "brand": "mybrand",
    "template": "ad-card",
    "size": "all",
    "badge": "NEW VIDEO",
    "title": "How to *automate* your workflow",
    "text": "Step-by-step guide to building your own stack.",
    "cta": "Watch now"
}
```

```bash
python generate.py content/my-post.json
```

### Batch (multiple items)

Top-level keys apply to all items. Each item can override them.

```json
{
    "brand": "mybrand",
    "size": "all",
    "items": [
        {"template": "ad-card", "title": "How to *automate*", "cta": "Watch"},
        {"template": "quote-card", "text": "Quality is a habit.", "attr": "Aristotle"},
        {"template": "tip-card", "badge": "PRO TIP", "title": "3 Ways to Automate", "bullets": "First|Second|Third"}
    ]
}
```

```bash
python generate.py content/week-posts.json
# -> 9 images (3 templates × 3 sizes)
```

### Classic CLI

```bash
# Instagram post (1080x1080) — default
python generate.py --brand mybrand --template quote-card \
    --text "Your quote here" --attr "Author Name"

# All sizes at once
python generate.py --brand mybrand --template ad-card --size all \
    --badge "NEW" --title "Big Announcement" --cta "Learn more"

# Background image with overlay
python generate.py --brand mybrand --template ad-card --size post \
    --title "Big Launch" --cta "Watch now" \
    --bg /path/to/photo.jpg --bg-opacity 0.7
```

### CLI via Docker

```bash
docker compose run --rm app python generate.py --brand example --template quote-card \
    --text "Docker CLI works" --size all
```

---

## Templates

| Template | Description | Params |
|----------|-------------|--------|
| **quote-card** | Quote with attribution. Clean, centered layout. | `text`, `attr`, `num` |
| **tip-card** | Badge + title + bullet points. Tips, checklists, how-tos. | `badge`, `title`, `bullets` (pipe-separated), `num` |
| **announcement** | Event or product announcement with CTA button. | `badge`, `title`, `date`, `attr`, `cta` |
| **ad-card** | Ad creative. `*asterisks*` render in accent color. | `badge`, `title`, `text`, `cta`, `urgency`, `attr` |

All templates support optional background image: `bg` (path) + `bg_opacity` (0-1).

---

## Sizes

| Name | Resolution | Use case |
|------|-----------|----------|
| `post` | 1080x1080 | Instagram/Facebook feed (default) |
| `story` | 1080x1920 | Instagram Story, Reels, TikTok, YouTube Shorts |
| `youtube` | 1280x720 | YouTube thumbnail |
| `all` | all above | Generates 3 files from one command |
| `WxH` | custom | e.g. `1200x628` for Open Graph |

---

## Safe Zones

Templates automatically apply safe-zone padding so nothing important gets hidden by platform UI.

| Format | Top | Bottom | Left | Right | What gets covered |
|--------|-----|--------|------|-------|-------------------|
| **Feed post** (1:1) | 80px | 80px | 80px | 80px | Minimal (profile grid crop) |
| **Story** (9:16) | 288px | 460px | 65px | 130px | Status bar, username, reply bar, action buttons |
| **YouTube thumb** (16:9) | 72px | 101px | 102px | 141px | Progress bar, duration badge |

---

## Create Your Brand

### Option 1: Brand Builder (panel)

Open `/panel/brands/builder` — pick colors, fonts, preview live, save.

### Option 2: AI-assisted

Download "AI Brand Instructions" from `/panel` and paste into ChatGPT/Claude with your brand guidelines. The AI generates a complete CSS file.

### Option 3: Manual

1. Copy `brands/_template.css` to `brands/mybrand.css`
2. Add a Google Fonts `@import` at the top
3. Fill in the `--brand-*` CSS variables
4. Test: `python generate.py --brand mybrand --template quote-card --text "Hello"`

See `brands/example.css` for a complete working reference.

### Brand tokens

| Token | Purpose |
|-------|---------|
| `--brand-bg-primary` | Page background |
| `--brand-accent` | Primary brand highlight color |
| `--brand-cta` | CTA button background |
| `--brand-cta-text` | Text color on CTA buttons |
| `--brand-text-primary` | Main text (highest contrast) |
| `--brand-text-secondary` | Secondary text |
| `--brand-text-muted` | Subtle text |
| `--brand-font-heading` | Heading font family |
| `--brand-font-body` | Body text font family |
| `--brand-font-mono` | Monospace font (badges, code) |
| `--brand-heading-weight` | Normal heading weight |
| `--brand-heading-weight-heavy` | Heavy heading weight |

Full list: `brands/_template.css`

### Keeping brands private

Brand files are `.gitignore`d by default (except `example.css` and `_template.css`).

```bash
# Use a custom brands directory
python generate.py --brand mybrand --brands-dir ~/my-brands --template quote-card --text "Hi"
```

Or create `config.json` (git-ignored):
```json
{"brands_dir": "/path/to/brands", "output_dir": "/path/to/output"}
```

---

## Adding Templates

Templates share common logic via two base files:

| File | What it provides |
|------|-----------------|
| `templates/_base.css` | CSS reset, body styles, safe zone variables, background image support |
| `templates/_base.js` | `initTemplate()` — brand CSS loading, bg injection. `autoSizeText()` — responsive text sizing |

Create `templates/my-template.html`, use `--brand-*` tokens for colors/fonts, `--safe-*` for padding, and `vw`/`vh` units for sizing. See existing templates for patterns.

---

## Configuration

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Session signing key |
| `DATABASE_URL` | No | `postgresql://...` for prod, empty for SQLite |
| `SMTP_HOST` | No | SMTP server (AWS SES, Resend, Mailgun, etc.) |
| `SMTP_PORT` | No | Default: 587 |
| `SMTP_USER` | No | SMTP username |
| `SMTP_PASS` | No | SMTP password |
| `EMAIL_FROM` | No | Sender email address |
| `WEBHOOK_SECRET` | No | Shared secret for credit webhook |
| `BASE_URL` | No | Public URL (default: `http://localhost:8000`) |

If `SMTP_HOST` is not set, magic links are printed to the console (dev mode).

If `DATABASE_URL` is not set, SQLite is used at `data/app.db`.

### Database

| Mode | `DATABASE_URL` | Backend |
|------|----------------|---------|
| Dev | empty | SQLite (`data/app.db`) |
| Prod | `postgresql://user:pass@host/db` | PostgreSQL |

`docker-compose.yml` includes a PostgreSQL service by default.

---

## Project Structure

```
social-media-generator/
├── generate.py              # CLI — renders templates via Playwright
├── engine.py                # Shared rendering logic (CLI + API)
├── app.py                   # FastAPI — API + user panel
├── db.py                    # Database layer (SQLite / PostgreSQL)
├── mailer.py                # Email via SMTP (any provider)
├── Dockerfile
├── docker-compose.yml       # App + PostgreSQL
├── .env.example
│
├── brands/
│   ├── _template.css        # Annotated template for new brands
│   └── example.css          # Working example brand
├── templates/
│   ├── _base.css            # Shared CSS: reset, safe zones
│   ├── _base.js             # Shared JS: initTemplate(), autoSizeText()
│   ├── quote-card.html
│   ├── tip-card.html
│   ├── announcement.html
│   └── ad-card.html
├── panel/                   # Jinja2 templates for user panel
│   ├── _layout.html
│   ├── login.html
│   ├── dashboard.html
│   ├── brands.html
│   ├── brand_builder.html
│   └── preview.html
├── static/
│   ├── panel.css
│   └── brand_builder.js
├── docs/
│   ├── ai-brand-instructions.md
│   └── claude-code-skill.md
├── content/
│   └── example.json         # Example batch input
└── data/                    # Runtime data (git-ignored)
    └── app.db               # SQLite (dev mode)
```

---

## License

MIT
