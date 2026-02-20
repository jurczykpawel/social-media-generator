"""
Rendering engine — shared by CLI (generate.py) and API (app.py).
Renders HTML templates with brand CSS via Playwright screenshots.
"""

import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

SIZES = {
    'post':    (1080, 1080),
    'story':   (1080, 1920),
    'youtube': (1280, 720),
}

SCRIPT_DIR = Path(__file__).parent.resolve()
TEMPLATES_DIR = SCRIPT_DIR / 'templates'
DEFAULT_BRANDS_DIR = SCRIPT_DIR / 'brands'

CONTENT_KEYS = [
    'text', 'attr', 'title', 'badge', 'bullets', 'number',
    'label', 'date', 'cta', 'num', 'urgency', 'bg_opacity',
]

META_KEYS = {'brand', 'template', 'size', 'output_prefix', 'output_dir', 'brands_dir'}


def parse_size(size_str: str) -> list:
    """Parse size string into list of (name, width, height) tuples."""
    if size_str == 'all':
        return [(name, w, h) for name, (w, h) in SIZES.items()]
    if size_str in SIZES:
        w, h = SIZES[size_str]
        return [(size_str, w, h)]
    if 'x' in size_str:
        parts = size_str.split('x')
        return [('custom', int(parts[0]), int(parts[1]))]
    raise ValueError(f"Unknown size '{size_str}'. Use: {', '.join(SIZES.keys())}, all, or WxH")


def validate_brand(brand: str, brands_dir: Path) -> Path:
    """Check brand CSS file exists, return its path."""
    path = brands_dir / f'{brand}.css'
    if not path.exists():
        available = sorted(f.stem for f in brands_dir.glob('*.css') if not f.stem.startswith('_'))
        raise FileNotFoundError(
            f"Brand '{brand}' not found in {brands_dir}/. "
            f"Available: {', '.join(available) if available else 'none'}"
        )
    return path


def validate_template(template: str) -> Path:
    """Check template HTML file exists, return its path."""
    path = TEMPLATES_DIR / f'{template}.html'
    if not path.exists():
        available = sorted(f.stem for f in TEMPLATES_DIR.glob('*.html') if not f.stem.startswith('_'))
        raise FileNotFoundError(
            f"Template '{template}' not found. Available: {', '.join(available)}"
        )
    return path


def list_templates() -> list[str]:
    """Return list of available template names."""
    return sorted(f.stem for f in TEMPLATES_DIR.glob('*.html') if not f.stem.startswith('_'))


def list_brands(brands_dir: Path) -> list[str]:
    """Return list of available brand names in a directory."""
    return sorted(f.stem for f in brands_dir.glob('*.css') if not f.stem.startswith('_'))


def build_url(template_path: Path, brand: str, brands_dir: Path, params: dict) -> str:
    """Build file:// URL with brand path and content params."""
    query = urllib.parse.urlencode({
        'brand': brand,
        'brands_dir': str(brands_dir),
        **params
    })
    return f'file://{template_path}?{query}'


def render_image(
    brand_css_path: Path,
    template: str,
    width: int,
    height: int,
    params: dict,
    page=None,
) -> bytes:
    """Render a single image. Returns PNG bytes.

    If `page` is provided, reuses existing Playwright page (faster for batch).
    If `page` is None, launches a new browser (simpler, used by API).
    """
    template_path = validate_template(template)
    url = build_url(template_path, brand_css_path.stem, brand_css_path.parent, params)

    if page is not None:
        page.set_viewport_size({'width': width, 'height': height})
        page.goto(url, wait_until='networkidle')
        page.wait_for_timeout(2000)
        return page.screenshot(type='png')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_viewport_size({'width': width, 'height': height})
        pg.goto(url, wait_until='networkidle')
        pg.wait_for_timeout(2000)
        png_bytes = pg.screenshot(type='png')
        browser.close()
        return png_bytes


def render_to_file(
    brand_css_path: Path,
    template: str,
    width: int,
    height: int,
    params: dict,
    output_path: Path,
    page=None,
) -> int:
    """Render image and save to file. Returns file size in bytes."""
    png_bytes = render_image(brand_css_path, template, width, height, params, page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(png_bytes)
    return len(png_bytes)
