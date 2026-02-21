# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-02-21

### Added

- CLI for rendering social media graphics from HTML templates
- FastAPI REST API with Bearer token authentication
- User panel with magic link login (no passwords)
- Credit-based usage system with atomic deduction
- Universal webhook for crediting users after payment (Bearer + HMAC auth)
- Product-to-credits mapping via `CREDIT_PRODUCTS` env var
- SQLite (dev) and PostgreSQL (production) database support
- Docker and docker-compose setup with health checks
- Brand builder with color pickers and font selectors
- CSS brand upload with injection prevention
- Optional Cloudflare Turnstile CAPTCHA on login
- CSRF protection on all state-changing panel endpoints
- Rate limiting on auth, API, and webhook endpoints
- Playwright SSRF prevention via network route filtering
- Session versioning for server-side logout invalidation
- 4 built-in templates: quote-card, tip-card, announcement, ad-card
- 3 output formats: Instagram post (1080x1080), Story (1080x1920), YouTube thumbnail (1280x720)
- Custom size support (WxH up to 4096x4096)
- 97 tests covering security, auth, API, webhooks, and rendering
- AI brand instructions and Claude Code skill downloads
- SMTP email with multi-provider support (AWS SES, Resend, Mailgun, SendGrid)
