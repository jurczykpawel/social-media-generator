# Contributing

Contributions are welcome! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/jurczykpawel/social-media-generator.git
cd social-media-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest httpx
python -m playwright install chromium
cp .env.example .env
```

## Running Tests

```bash
# All tests
pytest

# Verbose
pytest -v

# Single file
pytest test_app.py

# By keyword
pytest -k "webhook" -v
```

All tests must pass before submitting a PR.

## Project Structure

| File | Role |
|------|------|
| `app.py` | FastAPI — API + panel + auth |
| `engine.py` | Playwright rendering engine |
| `db.py` | SQLite/PostgreSQL database layer |
| `mailer.py` | SMTP email sender |
| `generate.py` | CLI entry point |
| `test_app.py` | Main test suite |
| `test_db.py` | Database tests |
| `test_engine.py` | Rendering engine tests |
| `conftest.py` | Pytest fixtures |

## Code Standards

- Python 3.10+
- Type hints on public functions
- Docstrings on modules and public functions
- All SQL queries must use parameterized placeholders (`%s` / `?`)
- Security-sensitive code must have tests

## Pull Request Process

1. Fork the repo and create a feature branch
2. Write or update tests for your changes
3. Run `pytest` and ensure all tests pass
4. Submit a PR with a clear description of what and why

## Adding a Template

1. Create `templates/your-template.html` following existing patterns
2. Use `_base.css` and `_base.js` includes
3. Support all content keys via URL query params
4. Test with: `python generate.py --brand example --template your-template --text "Test" --size all`

## Adding a Brand

Three options:
1. **CSS file** — copy `brands/_template.css`, fill in values, save as `brands/your-brand.css`
2. **Brand builder** — use the panel at `/panel/brands/builder`
3. **AI** — use the instructions in `docs/ai-brand-instructions.md`

## Reporting Issues

Use [GitHub Issues](https://github.com/jurczykpawel/social-media-generator/issues). Include:
- Python version (`python --version`)
- Steps to reproduce
- Expected vs actual behavior
- Error output (if any)
