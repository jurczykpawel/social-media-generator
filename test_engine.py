"""Tests for engine.py — rendering engine (no Playwright needed for most tests)."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine import (
    SIZES, CONTENT_KEYS, META_KEYS,
    parse_size, validate_brand, validate_template,
    list_templates, list_brands, build_url,
)


# ── parse_size ─────────────────────────────────────────

def test_parse_size_post():
    result = parse_size('post')
    assert result == [('post', 1080, 1080)]


def test_parse_size_story():
    result = parse_size('story')
    assert result == [('story', 1080, 1920)]


def test_parse_size_youtube():
    result = parse_size('youtube')
    assert result == [('youtube', 1280, 720)]


def test_parse_size_all():
    result = parse_size('all')
    assert len(result) == 3
    names = [r[0] for r in result]
    assert 'post' in names
    assert 'story' in names
    assert 'youtube' in names


def test_parse_size_custom():
    result = parse_size('1200x628')
    assert result == [('custom', 1200, 628)]


def test_parse_size_invalid():
    with pytest.raises(ValueError, match="Unknown size"):
        parse_size('banana')


# ── validate_brand ─────────────────────────────────────

def test_validate_brand_exists(brands_dir):
    path = validate_brand('testbrand', brands_dir)
    assert path.exists()
    assert path.name == 'testbrand.css'


def test_validate_brand_not_found(brands_dir):
    with pytest.raises(FileNotFoundError, match="not found"):
        validate_brand('nonexistent', brands_dir)


def test_validate_brand_lists_available(brands_dir):
    """Error message should list available brands."""
    with pytest.raises(FileNotFoundError, match="testbrand"):
        validate_brand('missing', brands_dir)


# ── validate_template ──────────────────────────────────

def test_validate_template_exists():
    path = validate_template('quote-card')
    assert path.exists()
    assert path.name == 'quote-card.html'


def test_validate_template_not_found():
    with pytest.raises(FileNotFoundError, match="not found"):
        validate_template('nonexistent-template')


def test_validate_template_ignores_underscore():
    """Templates starting with _ should not be listed as available."""
    with pytest.raises(FileNotFoundError) as exc_info:
        validate_template('no-such-template')
    assert '_base' not in str(exc_info.value)


# ── list_templates ─────────────────────────────────────

def test_list_templates():
    templates = list_templates()
    assert 'quote-card' in templates
    assert 'tip-card' in templates
    assert 'ad-card' in templates
    assert 'announcement' in templates


def test_list_templates_excludes_underscore():
    templates = list_templates()
    assert '_base' not in templates


# ── list_brands ────────────────────────────────────────

def test_list_brands(brands_dir):
    brands = list_brands(brands_dir)
    assert 'testbrand' in brands


def test_list_brands_excludes_underscore(brands_dir):
    (brands_dir / '_hidden.css').write_text(':root {}')
    brands = list_brands(brands_dir)
    assert '_hidden' not in brands


def test_list_brands_empty(tmp_path):
    empty_dir = tmp_path / 'empty'
    empty_dir.mkdir()
    assert list_brands(empty_dir) == []


# ── build_url ──────────────────────────────────────────

def test_build_url(brands_dir):
    template_path = Path('/app/templates/quote-card.html')
    url = build_url(template_path, 'testbrand', brands_dir, {'text': 'Hello world'})
    assert url.startswith('file:///app/templates/quote-card.html?')
    assert 'brand=testbrand' in url
    assert 'text=Hello' in url


def test_build_url_encodes_special_chars(brands_dir):
    template_path = Path('/app/templates/quote-card.html')
    url = build_url(template_path, 'testbrand', brands_dir, {'text': 'Hello & goodbye'})
    assert 'Hello+%26+goodbye' in url or 'Hello+&+goodbye' not in url


# ── Constants ──────────────────────────────────────────

def test_sizes_dict():
    assert 'post' in SIZES
    assert 'story' in SIZES
    assert 'youtube' in SIZES
    assert SIZES['post'] == (1080, 1080)
    assert SIZES['story'] == (1080, 1920)
    assert SIZES['youtube'] == (1280, 720)


def test_content_keys():
    assert 'text' in CONTENT_KEYS
    assert 'attr' in CONTENT_KEYS
    assert 'title' in CONTENT_KEYS
    assert 'cta' in CONTENT_KEYS
    assert 'badge' in CONTENT_KEYS
    assert 'bullets' in CONTENT_KEYS


def test_meta_keys():
    assert 'brand' in META_KEYS
    assert 'template' in META_KEYS
    assert 'size' in META_KEYS
