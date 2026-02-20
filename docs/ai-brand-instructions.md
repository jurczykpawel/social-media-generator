# AI Brand CSS Generation Instructions

Use this prompt with ChatGPT, Claude, or any AI assistant to generate a brand CSS file for the Social Media Graphics Generator.

---

## Prompt

Copy and paste the following into your AI assistant:

---

I need you to generate a brand CSS file for a social media graphics generator. The tool uses CSS custom properties (variables) to theme HTML templates.

**My brand:**
- Brand name: [YOUR BRAND NAME]
- Website/tagline: [YOUR WEBSITE OR TAGLINE]
- Primary color: [YOUR MAIN BRAND COLOR, e.g., #2DD4BF]
- Secondary/CTA color: [YOUR CTA COLOR, e.g., #F97316]
- Theme: [dark or light]
- Preferred fonts: [e.g., Inter for body, Space Grotesk for headings, or "choose for me"]

**Generate a CSS file with this exact structure:**

```css
@import url('https://fonts.googleapis.com/css2?family=HEADING_FONT:wght@400;500;600;700&family=BODY_FONT:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    /* Identity — displayed in template footers */
    --brand-name: "Brand Name";
    --brand-tagline: "// tagline";

    /* Backgrounds */
    --brand-bg-primary: ;     /* Main page background */
    --brand-bg-secondary: ;   /* Slightly different bg */
    --brand-bg-surface: ;     /* Interactive surface */
    --brand-bg-card: ;        /* Card background */

    /* Accent color — primary brand highlight */
    --brand-accent: ;
    --brand-accent-hover: ;   /* Slightly lighter/brighter */
    --brand-accent-dim: ;     /* Very transparent, rgba(..., 0.10) */

    /* CTA color — call-to-action buttons */
    --brand-cta: ;
    --brand-cta-hover: ;
    --brand-cta-text: ;       /* Text color ON the CTA background */

    /* Text colors */
    --brand-text-primary: ;   /* Main text, highest contrast */
    --brand-text-secondary: ; /* Secondary text */
    --brand-text-muted: ;     /* Subtle text (WCAG AA min 4.5:1 contrast) */

    /* Borders & Shadows */
    --brand-border: ;         /* e.g., rgba(255, 255, 255, 0.06) for dark */
    --brand-border-accent: ;  /* e.g., rgba(accent, 0.15) */
    --brand-shadow-sm: ;
    --brand-shadow-md: ;

    /* Semantic colors */
    --brand-success: #34D399;
    --brand-error: #EF4444;

    /* Typography */
    --brand-font-heading: 'Font Name', system-ui, sans-serif;
    --brand-font-body: 'Font Name', system-ui, sans-serif;
    --brand-font-mono: 'JetBrains Mono', monospace;
    --brand-heading-weight: 700;
    --brand-heading-weight-heavy: 700;

    /* Border radius */
    --brand-radius-sm: 6px;
    --brand-radius-md: 10px;
    --brand-radius-lg: 16px;

    /* Theme hint */
    --brand-theme: dark; /* or light */

    /* Badge backgrounds — subtle tinted bg */
    --brand-badge-accent-bg: ;  /* rgba(accent, 0.12) */
    --brand-badge-cta-bg: ;     /* rgba(cta, 0.12) */
    --brand-badge-success-bg: rgba(52, 211, 153, 0.08);
}
```

**Rules:**
1. ALL variables must have values — no empty ones
2. Use the Google Fonts @import at the top with the exact fonts you chose
3. For dark theme: dark backgrounds (#0x-#1x range), light text (#E-#F range)
4. For light theme: light backgrounds (#F range), dark text (#1-#3 range)
5. Ensure WCAG AA contrast (4.5:1) between text-primary and bg-primary
6. The CTA color should contrast well with cta-text
7. Accent-dim should be a very transparent version of accent (opacity ~0.10)
8. Badge backgrounds should be subtle tinted versions (opacity ~0.12)

**Output only the CSS file, no explanations.**

---

## How to use the generated file

1. Save the AI output as `mybrand.css`
2. Upload it via the Brand panel, or place it in the `brands/` directory
3. Test: generate an image with your brand to verify colors and fonts look correct
