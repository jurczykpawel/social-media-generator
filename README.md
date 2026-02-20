# Social Media Graphics Generator

**One text, multiple formats.** Generate brand-consistent social media graphics from HTML templates. Instagram posts, Stories, YouTube thumbnails — all pixel-perfect, all on-brand.

HTML templates use CSS custom properties (`--brand-*`) for theming. A Python script renders them via headless Chromium (Playwright) and saves PNGs. No Photoshop, no Canva, no manual resizing.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Templates](#templates)
- [Sizes](#sizes)
- [Safe Zones](#safe-zones)
- [Create Your Brand](#create-your-brand)
- [Adding Templates](#adding-templates)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [License](#license)

---

## How It Works

```
brands/mybrand.css        templates/quote-card.html        generate.py
  --brand-accent: #2DD4BF    color: var(--brand-accent)      Playwright screenshot
  --brand-font: 'Inter'      font: var(--brand-font)            ↓
       ↓                          ↓                         output/
       └──────────── merge ───────┘                    mybrand_quote-card_post_1080x1080.png
                                                       mybrand_quote-card_story_1080x1920.png
                                                       mybrand_quote-card_youtube_1280x720.png
```

1. **Brand** = CSS file with `--brand-*` color/font tokens
2. **Template** = HTML file that reads those tokens
3. **Generator** = Playwright opens the template in headless Chromium, sets viewport to target size, takes a screenshot

Same template, same text — three formats from one command.

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/user/social-media-generator.git
cd social-media-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# 2. Generate with the included example brand
python generate.py --brand example --template quote-card \
    --text "Ship it before it's perfect." --attr "A wise engineer"

# 3. Check output/
open output/example_quote-card_post_1080x1080.png
```

---

## Usage

### From JSON (recommended)

The simplest workflow — prepare content in a JSON file, run one command.

**Single item:**

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

**Multiple items with shared defaults:**

Top-level keys apply to all items. Each item can override them.

```json
{
    "brand": "mybrand",
    "size": "all",
    "items": [
        {
            "template": "ad-card",
            "badge": "NEW VIDEO",
            "title": "How to *automate* your workflow",
            "cta": "Watch now",
            "output_prefix": "ad_001"
        },
        {
            "template": "quote-card",
            "text": "Quality is not an act, it is a habit.",
            "attr": "Aristotle",
            "output_prefix": "quote_002"
        },
        {
            "template": "tip-card",
            "badge": "PRO TIP",
            "title": "3 Ways to Automate Without SaaS",
            "bullets": "Self-host your workflow engine|Docker Compose on a VPS|Webhooks + cron = free scheduler",
            "output_prefix": "tip_003"
        }
    ]
}
```

```bash
python generate.py content/week-posts.json
# -> 9 images (3 templates × 3 sizes)
```

**CLI overrides** — any flag overrides JSON values for all items:

```bash
python generate.py content/posts.json --brand otherbrand
python generate.py content/posts.json --size youtube
```

**Plain array** is also supported (each item must include `brand` and `template`):

```json
[
    {"brand": "mybrand", "template": "quote-card", "text": "Hello", "attr": "Author"},
    {"brand": "mybrand", "template": "ad-card", "title": "Big News", "cta": "Watch"}
]
```

### AI Workflow

This tool pairs well with an AI assistant:

1. Describe what you need — "prepare 5 posts for this week about n8n automation"
2. AI generates a JSON file with all content, templates, and brand settings
3. Run: `python generate.py content/week-posts.json`
4. Done — all images in `output/`

### Classic CLI

For quick one-off generation without a JSON file:

```bash
# Instagram post (1080x1080) — default
python generate.py --brand mybrand --template quote-card \
    --text "Your quote here" --attr "Author Name"

# YouTube thumbnail (1280x720)
python generate.py --brand mybrand --template ad-card --size youtube \
    --title "How to *automate* everything" --cta "Watch now"

# All sizes at once (post + story + youtube)
python generate.py --brand mybrand --template ad-card --size all \
    --badge "NEW" --title "Big Announcement" --cta "Learn more"

# Background image with overlay
python generate.py --brand mybrand --template ad-card --size post \
    --title "Big Launch" --cta "Watch now" \
    --bg /path/to/photo.jpg --bg-opacity 0.7
```

Background image works in JSON too: `"bg": "./images/photo.jpg", "bg_opacity": "0.7"`

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

Social media platforms overlay UI elements on content (usernames, like buttons, reply bars). Templates automatically apply safe-zone padding so nothing important gets hidden.

| Format | Top | Bottom | Left | Right | What gets covered |
|--------|-----|--------|------|-------|-------------------|
| **Feed post** (1:1) | 80px | 80px | 80px | 80px | Minimal (profile grid crop) |
| **Story** (9:16) | 288px | 460px | 65px | 130px | Status bar, username, reply bar, action buttons |
| **YouTube thumb** (16:9) | 72px | 101px | 102px | 141px | Progress bar, duration badge |

Story footer bar is automatically repositioned above the platform UI zone (~326px from bottom).

Safe zone values are based on the most conservative platform requirements. Sources:
- [Instagram Safe Zone 2026](https://www.outfy.com/blog/instagram-safe-zone/)
- [TikTok, IG & Facebook Safe Zones 2025](https://www.ugcfactory.io/blog/the-ultimate-guide-to-safe-zones-for-tiktok-facebook-and-instagram-stories-reels-2025)
- [YouTube Thumbnail Safe Zone](https://www.thumix.com/blog/youtube-thumbnail-safe-zone)
- [YouTube Shorts Dimensions & Safe Zones](https://getkoro.app/blog/youtube-shorts-dimensions)

---

## Create Your Brand

1. Copy `brands/_template.css` to `brands/mybrand.css`
2. Add a Google Fonts `@import` at the top
3. Fill in the `--brand-*` CSS variables (colors, fonts, etc.)
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
| `--brand-shadow-md` | Medium box-shadow |
| `--brand-radius-sm` | Small border-radius |

Full list with descriptions: `brands/_template.css`

### Keeping brands private

Brand files are `.gitignore`d by default (except `example.css` and `_template.css`).

**Option A:** Use `--brands-dir`
```bash
python generate.py --brand mybrand --brands-dir ~/my-brands --template quote-card --text "Hi"
```

**Option B:** Create `config.json` (git-ignored)
```json
{
    "brands_dir": "/path/to/my/brands",
    "output_dir": "/path/to/output"
}
```

Priority: CLI flags > config.json > defaults (`./brands`, `./output`)

---

## Adding Templates

### Architecture

Templates share common logic via two base files — edit once, all templates benefit:

| File | What it provides |
|------|-----------------|
| `templates/_base.css` | CSS reset, body styles, safe zone variables, background image support |
| `templates/_base.js` | `initTemplate()` — brand CSS loading, bg injection. `autoSizeText()` — responsive text sizing |

### Creating a new template

**1. Create `templates/my-template.html`:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1080">
<title>My Template</title>
<link rel="stylesheet" href="_base.css">
<link id="brand-css" rel="stylesheet" href="">
<style>
  .card {
    position: relative;
    z-index: 1;
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    padding: var(--safe-top) var(--safe-right)
             calc(var(--safe-bottom) + var(--footer-height)) var(--safe-left);
    text-align: center;
  }

  .title {
    font-family: var(--brand-font-heading);
    font-weight: var(--brand-heading-weight-heavy);
    color: var(--brand-text-primary);
    line-height: 1.15;
  }

  .footer {
    position: absolute;
    bottom: var(--footer-bottom);
    left: 0; right: 0;
    height: var(--footer-height);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--brand-accent);
    z-index: 2;
  }

  /* Per-format adjustments */
  @media (max-aspect-ratio: 3/4) { /* Story */ }
  @media (min-aspect-ratio: 4/3) { /* YouTube */ }
</style>
</head>
<body>

<div class="card">
  <div class="title" id="title">Title Here</div>
</div>

<div class="footer">
  <span class="footer-name" id="footerName"></span>
</div>

<script src="_base.js"></script>
<script>
  initTemplate(({ params, styles, brandName }) => {
    document.getElementById('footerName').textContent = brandName;

    const title = params.get('title');
    if (title) document.getElementById('title').textContent = title;

    autoSizeText(document.getElementById('title'), [
      [30, 5.5], [60, 4.5], [100, 3.8], [Infinity, 3]
    ], 0.35);
  });
</script>
</body>
</html>
```

**2. Register new URL params** (if needed):

Content params are passed as URL query parameters. If your template uses existing params, it works automatically:

```python
# generate.py
CONTENT_KEYS = ['text', 'attr', 'title', 'badge', 'bullets', 'number',
                'label', 'date', 'cta', 'num', 'urgency', 'bg_opacity']
```

To add a new param (e.g. `--subtitle`): add `'subtitle'` to `CONTENT_KEYS` and add `parser.add_argument('--subtitle')`.

**3. Test across all sizes:**

```bash
python generate.py --brand example --template my-template --size all --title "Hello World"
```

### Key conventions

- Use `--brand-*` tokens for colors/fonts, never hardcode
- Use `--safe-*` variables for padding, never hardcode margins
- Use `vw`/`vh` units for all sizes — same template renders at 1080x1080, 1080x1920, and 1280x720
- Use `@media (max-aspect-ratio: 3/4)` for story tweaks, `@media (min-aspect-ratio: 4/3)` for YouTube tweaks
- Hide unused elements: `if (param) el.textContent = param; else el.style.display = 'none';`

### `initTemplate(callback)` provides:

| Property | Description |
|----------|-------------|
| `params` | `URLSearchParams` with all query params |
| `styles` | `getComputedStyle(document.documentElement)` |
| `brandName` | String from `--brand-name` CSS variable |

### `autoSizeText(element, breakpoints, maxHeightRatio)`:

| Param | Description |
|-------|-------------|
| `element` | DOM element to resize |
| `breakpoints` | `[maxChars, vwMultiplier]` pairs, sorted ascending. Last = `Infinity` |
| `maxHeightRatio` | Max fraction of viewport height before shrinking (default: `0.35`) |

Example: `[[30, 5.5], [60, 4.5], [Infinity, 3]]` — under 30 chars = 5.5vw, under 60 = 4.5vw, else 3vw.

---

## Project Structure

```
social-media-generator/
├── generate.py              # CLI — renders templates via Playwright
├── brands/
│   ├── _template.css        # Annotated template for new brands
│   ├── example.css          # Working example brand (included in repo)
│   └── mybrand.css          # Your brand (git-ignored)
├── templates/
│   ├── _base.css            # Shared CSS: reset, safe zones, bg support
│   ├── _base.js             # Shared JS: initTemplate(), autoSizeText()
│   ├── quote-card.html      # Quote + attribution
│   ├── tip-card.html        # Badge + title + bullet list
│   ├── announcement.html    # Event + date + CTA
│   └── ad-card.html         # Ad creative with accent words
├── content/
│   └── example.json         # Example batch input
├── output/                  # Generated PNGs (git-ignored)
├── config.json.example      # Sample config for custom paths
└── requirements.txt         # Python dependencies
```

---

## Requirements

- Python 3.8+
- [Playwright](https://playwright.dev/python/) (`pip install playwright`)
- Chromium (`python -m playwright install chromium`)

---

## License

MIT
