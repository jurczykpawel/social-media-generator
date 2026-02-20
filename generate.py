#!/usr/bin/env python3
"""
Social Media Graphics Generator
Renders HTML templates with brand-specific styling via Playwright screenshots.

Usage:
  # Simplest — AI generates JSON, human runs one command:
  python generate.py posts.json

  # Override brand or size for all items:
  python generate.py posts.json --brand otherbrand --size youtube

  # Classic CLI (all params inline):
  python generate.py --brand example --template quote-card --text "Hello"

Brand CSS files are loaded from a configurable directory (--brands-dir or config.json).
This keeps proprietary brand data separate from the tool itself.
"""

import argparse
import json
import sys
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
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / 'output'
CONFIG_FILE = SCRIPT_DIR / 'config.json'

CONTENT_KEYS = ['text', 'attr', 'title', 'badge', 'bullets', 'number', 'label', 'date', 'cta', 'num', 'urgency', 'bg_opacity']
META_KEYS = {'brand', 'template', 'size', 'output_prefix', 'output_dir', 'brands_dir'}


def load_config() -> dict:
    """Load config.json if it exists. Returns empty dict otherwise."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def resolve_dirs(args, config: dict) -> tuple:
    """Resolve brands_dir and output_dir from CLI > config > defaults."""
    brands_dir = Path(args.brands_dir) if args.brands_dir else \
                 Path(config['brands_dir']) if 'brands_dir' in config else \
                 DEFAULT_BRANDS_DIR
    output_dir = Path(args.output_dir) if args.output_dir else \
                 Path(config['output_dir']) if 'output_dir' in config else \
                 DEFAULT_OUTPUT_DIR
    return brands_dir.resolve(), output_dir.resolve()


def validate_brand(brand: str, brands_dir: Path) -> Path:
    path = brands_dir / f'{brand}.css'
    if not path.exists():
        available = sorted(f.stem for f in brands_dir.glob('*.css') if not f.stem.startswith('_'))
        print(f"Error: Brand '{brand}' not found in {brands_dir}/", file=sys.stderr)
        if available:
            print(f"  Available: {', '.join(available)}", file=sys.stderr)
        else:
            print(f"  No brand files found. Create one from _template.css", file=sys.stderr)
        sys.exit(1)
    return path


def validate_template(template: str) -> Path:
    path = TEMPLATES_DIR / f'{template}.html'
    if not path.exists():
        available = sorted(f.stem for f in TEMPLATES_DIR.glob('*.html') if not f.stem.startswith('_'))
        print(f"Error: Template '{template}' not found. Available: {', '.join(available)}", file=sys.stderr)
        sys.exit(1)
    return path


def parse_size(size_str: str) -> list:
    if size_str == 'all':
        return [(name, w, h) for name, (w, h) in SIZES.items()]
    if size_str in SIZES:
        w, h = SIZES[size_str]
        return [(size_str, w, h)]
    if 'x' in size_str:
        parts = size_str.split('x')
        return [('custom', int(parts[0]), int(parts[1]))]
    print(f"Error: Unknown size '{size_str}'. Use: {', '.join(SIZES.keys())}, all, or WxH", file=sys.stderr)
    sys.exit(1)


def build_url(template_path: Path, brand: str, brands_dir: Path, params: dict) -> str:
    """Build file:// URL with brand path and content params."""
    query = urllib.parse.urlencode({
        'brand': brand,
        'brands_dir': str(brands_dir),
        **params
    })
    return f'file://{template_path}?{query}'


def generate_image(page, url: str, width: int, height: int, output_path: Path):
    page.set_viewport_size({'width': width, 'height': height})
    page.goto(url, wait_until='networkidle')
    page.wait_for_timeout(2000)
    page.screenshot(path=str(output_path), type='png')
    size_kb = output_path.stat().st_size / 1024
    print(f'  -> {output_path.name} ({width}x{height}, {size_kb:.0f} KB)')


def load_json_input(json_path: Path) -> tuple:
    """Load JSON file and normalize to (defaults_dict, items_list).

    Supports 3 formats:
      1. Single object:       {"brand":"x", "template":"y", "title":"..."}
      2. Array of objects:    [{"brand":"x", ...}, {"brand":"x", ...}]
      3. Object with items:   {"brand":"x", "size":"all", "items":[{...}, {...}]}
         Top-level keys are defaults, merged into each item.
    """
    with open(json_path) as f:
        data = json.load(f)

    if isinstance(data, list):
        return {}, data
    elif isinstance(data, dict):
        if 'items' in data:
            items = data.pop('items')
            return data, items
        else:
            return {}, [data]
    else:
        print(f"Error: JSON must be an object or array, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)


def generate_from_json(json_path: Path, cli_overrides: dict,
                       brands_dir: Path, output_dir: Path):
    """Generate images from a JSON file. CLI flags override JSON values."""
    defaults, items = load_json_input(json_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    total_images = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for i, item in enumerate(items, 1):
            # Merge: item values < JSON defaults < CLI overrides
            merged = {**defaults, **item}
            for k, v in cli_overrides.items():
                if v is not None:
                    merged[k] = v

            # Extract meta fields
            brand = merged.get('brand')
            if not brand:
                print(f"Error: Item {i} has no 'brand'. Set it in JSON or use --brand on CLI.", file=sys.stderr)
                sys.exit(1)
            validate_brand(brand, brands_dir)

            template = merged.get('template')
            if not template:
                print(f"Error: Item {i} has no 'template'. Set it in JSON.", file=sys.stderr)
                sys.exit(1)
            template_path = validate_template(template)

            size_name = merged.get('size', 'post')
            sizes = parse_size(size_name)

            # Content params = everything except meta keys
            params = {k: v for k, v in merged.items() if k not in META_KEYS}
            if 'bg' in params:
                params['bg'] = str(Path(params['bg']).resolve())

            prefix = merged.get('output_prefix', f'{brand}_{template}_{i:03d}')
            url = build_url(template_path, brand, brands_dir, params)

            preview = params.get('text', params.get('title', ''))[:50]
            print(f'[{i}/{len(items)}] {template}: {preview}...')

            for sn, w, h in sizes:
                filename = f'{prefix}_{sn}_{w}x{h}.png'
                output_path = output_dir / filename
                generate_image(page, url, w, h, output_path)
                total_images += 1

        browser.close()

    print(f'\nDone. {total_images} image(s) from {len(items)} item(s) in {output_dir}/')


def generate_single(brand: str, template: str, sizes: list, params: dict,
                     brands_dir: Path, output_dir: Path, output_prefix: str = None):
    validate_brand(brand, brands_dir)
    template_path = validate_template(template)
    output_dir.mkdir(parents=True, exist_ok=True)

    url = build_url(template_path, brand, brands_dir, params)
    prefix = output_prefix or f'{brand}_{template}'

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for size_name, width, height in sizes:
            filename = f'{prefix}_{size_name}_{width}x{height}.png'
            output_path = output_dir / filename
            generate_image(page, url, width, height, output_path)

        browser.close()

    print(f'\nDone. {len(sizes)} image(s) in {output_dir}/')


def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description='Social Media Graphics Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Examples:
  # From JSON (simplest — one command, AI generates the JSON):
  %(prog)s content/posts.json
  %(prog)s content/posts.json --brand otherbrand
  %(prog)s content/posts.json --size youtube

  # Classic CLI (all params inline):
  %(prog)s --brand example --template quote-card --text "Hello World" --attr "Author"
  %(prog)s --brand mybrand --template ad-card --size all --title "Big Launch"
''')
    # JSON input (positional, optional)
    parser.add_argument('json_file', nargs='?', help='JSON file with content (single object, array, or {defaults + items})')

    # Core args
    parser.add_argument('--brand', help='Brand name (overrides JSON)')
    parser.add_argument('--template', help='Template name (e.g., quote-card, tip-card, ad-card)')
    parser.add_argument('--size', help='post, story, youtube, all, or WxH (overrides JSON)')
    parser.add_argument('--batch', help='[Legacy] Path to JSON batch file (use positional arg instead)')
    parser.add_argument('--output-prefix', help='Custom output filename prefix')

    # Directory overrides
    parser.add_argument('--brands-dir', help='Path to brand CSS files (default: ./brands or config.json)')
    parser.add_argument('--output-dir', help='Path for generated PNGs (default: ./output or config.json)')

    # Content params (passed to template via URL)
    parser.add_argument('--text', help='Main text / quote')
    parser.add_argument('--attr', help='Attribution / author / subtext')
    parser.add_argument('--title', help='Headline (use *word* for accent color)')
    parser.add_argument('--badge', help='Badge/tag text')
    parser.add_argument('--bullets', help='Bullet points (pipe-separated: "A|B|C")')
    parser.add_argument('--number', help='Big number for stats')
    parser.add_argument('--label', help='Label text')
    parser.add_argument('--date', help='Date text')
    parser.add_argument('--cta', help='CTA button text')
    parser.add_argument('--num', help='Card/episode number')
    parser.add_argument('--urgency', help='Urgency text (e.g., "Limited spots")')
    parser.add_argument('--bg', help='Background image path (absolute or relative)')
    parser.add_argument('--bg-opacity', help='Overlay opacity over bg image (0-1, default: 0.65)')

    args = parser.parse_args()
    brands_dir, output_dir = resolve_dirs(args, config)

    # Mode 1: JSON file (new simple mode)
    if args.json_file:
        json_path = Path(args.json_file)
        if not json_path.exists():
            print(f"Error: File not found: {json_path}", file=sys.stderr)
            sys.exit(1)

        # Collect CLI overrides (only explicitly set values)
        cli_overrides = {}
        if args.brand: cli_overrides['brand'] = args.brand
        if args.size: cli_overrides['size'] = args.size
        if args.template: cli_overrides['template'] = args.template
        if args.output_prefix: cli_overrides['output_prefix'] = args.output_prefix
        for key in CONTENT_KEYS:
            val = getattr(args, key, None)
            if val is not None:
                cli_overrides[key] = val
        if args.bg:
            cli_overrides['bg'] = str(Path(args.bg).resolve())

        generate_from_json(json_path, cli_overrides, brands_dir, output_dir)

    # Mode 2: Legacy --batch
    elif args.batch:
        if not args.brand:
            parser.error('--brand is required with --batch')
        generate_batch(args.brand, Path(args.batch), brands_dir, output_dir)

    # Mode 3: Classic inline CLI
    elif args.template:
        if not args.brand:
            brand = config.get('default_brand')
            if not brand:
                parser.error('--brand is required (or set default_brand in config.json)')
        else:
            brand = args.brand
        sizes = parse_size(args.size or 'post')
        content_params = {}
        for key in CONTENT_KEYS:
            val = getattr(args, key, None)
            if val is not None:
                content_params[key] = val
        if args.bg:
            content_params['bg'] = str(Path(args.bg).resolve())
        generate_single(brand, args.template, sizes, content_params,
                        brands_dir, output_dir, args.output_prefix)
    else:
        parser.error('Provide a JSON file or use --template')


def generate_batch(brand: str, batch_file: Path, brands_dir: Path, output_dir: Path):
    """Legacy batch mode — kept for backwards compatibility."""
    validate_brand(brand, brands_dir)

    with open(batch_file) as f:
        items = json.load(f)

    output_dir.mkdir(parents=True, exist_ok=True)
    total_images = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for i, item in enumerate(items, 1):
            template = item.get('template', 'quote-card')
            template_path = validate_template(template)
            size_name = item.get('size', 'post')
            sizes = parse_size(size_name)

            params = {k: v for k, v in item.items() if k not in ('template', 'size', 'output_prefix')}
            if 'bg' in params:
                params['bg'] = str(Path(params['bg']).resolve())
            prefix = item.get('output_prefix', f'{brand}_{template}_{i:03d}')

            url = build_url(template_path, brand, brands_dir, params)
            preview = params.get('text', params.get('title', ''))[:50]
            print(f'[{i}/{len(items)}] {template}: {preview}...')

            for sn, w, h in sizes:
                filename = f'{prefix}_{sn}_{w}x{h}.png'
                output_path = output_dir / filename
                generate_image(page, url, w, h, output_path)
                total_images += 1

        browser.close()

    print(f'\nDone. {total_images} image(s) from {len(items)} item(s) in {output_dir}/')


if __name__ == '__main__':
    main()
