---
description: Create brand CSS files for the Social Media Graphics Generator. Use when the user says "create brand", "new brand", "stwórz brand", "nowy brand", or wants to generate a brand CSS file for social media graphics.
---

# Brand CSS Generator

You help users create brand CSS files for the Social Media Graphics Generator tool.

## Process

1. **Ask the user** for their brand details:
   - Brand name and tagline/website
   - Primary brand color (accent)
   - CTA/secondary color
   - Theme preference: dark or light
   - Font preferences (or suggest based on brand style)

2. **Read the template** at `brands/_template.css` to get the full list of required CSS variables.

3. **Generate the CSS file** following these rules:
   - ALL `--brand-*` variables must have values
   - Include Google Fonts `@import` at the top
   - For dark themes: backgrounds in #0x-#1x range, text in #E-#F range
   - For light themes: backgrounds in #F range, text in #1-#3 range
   - Ensure WCAG AA contrast (4.5:1 minimum) between text and background
   - `--brand-accent-dim` = accent color at ~10% opacity (rgba)
   - `--brand-badge-*-bg` = tinted backgrounds at ~12% opacity
   - `--brand-cta-text` must contrast well against `--brand-cta`

4. **Save the file** to `brands/{brandname}.css`

5. **Test** by running:
   ```bash
   python generate.py --brand {brandname} --template quote-card --size all --text "Test quote" --attr "Author"
   ```

6. **Show the user** the output paths and ask if they want adjustments.

## Example output

```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --brand-name: "your.brand";
    --brand-tagline: "// your.brand";
    --brand-bg-primary: #0F1117;
    --brand-bg-secondary: #151720;
    --brand-bg-surface: #1C1E2A;
    --brand-bg-card: #191B25;
    --brand-accent: #2DD4BF;
    --brand-accent-hover: #5EEAD4;
    --brand-accent-dim: rgba(45, 212, 191, 0.10);
    --brand-cta: #F97316;
    --brand-cta-hover: #FB923C;
    --brand-cta-text: #0F1117;
    --brand-text-primary: #F1F5F9;
    --brand-text-secondary: #94A3B8;
    --brand-text-muted: #64748B;
    --brand-border: rgba(255, 255, 255, 0.06);
    --brand-border-accent: rgba(45, 212, 191, 0.15);
    --brand-shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.2), 0 1px 3px rgba(0, 0, 0, 0.15);
    --brand-shadow-md: 0 4px 16px rgba(0, 0, 0, 0.25), 0 2px 6px rgba(0, 0, 0, 0.2);
    --brand-success: #34D399;
    --brand-error: #EF4444;
    --brand-font-heading: 'Space Grotesk', system-ui, sans-serif;
    --brand-font-body: 'Inter', system-ui, sans-serif;
    --brand-font-mono: 'JetBrains Mono', monospace;
    --brand-heading-weight: 700;
    --brand-heading-weight-heavy: 700;
    --brand-radius-sm: 6px;
    --brand-radius-md: 10px;
    --brand-radius-lg: 16px;
    --brand-theme: dark;
    --brand-badge-accent-bg: #132624;
    --brand-badge-cta-bg: #231910;
    --brand-badge-success-bg: #111E18;
}
```

## Reference

- Template with all variables: `brands/_template.css`
- Working example: `brands/example.css`
- Templates that use brand tokens: `templates/quote-card.html`, `templates/tip-card.html`, `templates/announcement.html`, `templates/ad-card.html`
