// Brand builder — live preview updates

const form = document.getElementById('builderForm');
const preview = document.getElementById('previewBox');

const DARK_DEFAULTS = {
  bg_primary: '#0F1117', bg_secondary: '#151720',
  text_primary: '#F1F5F9', text_secondary: '#94A3B8', text_muted: '#64748B',
  accent: '#2DD4BF', cta: '#F97316', cta_text: '#0F1117',
};

const LIGHT_DEFAULTS = {
  bg_primary: '#FAFBFD', bg_secondary: '#F0F2F5',
  text_primary: '#1A2332', text_secondary: '#4A5568', text_muted: '#94A3B8',
  accent: '#0064BC', cta: '#34D399', cta_text: '#FFFFFF',
};

function applyDefaults() {
  const theme = form.querySelector('input[name="theme"]:checked').value;
  const defaults = theme === 'dark' ? DARK_DEFAULTS : LIGHT_DEFAULTS;
  for (const [key, val] of Object.entries(defaults)) {
    const input = form.querySelector(`[name="${key}"]`);
    if (input) input.value = val;
  }
  updatePreview();
}

function updatePreview() {
  const get = name => form.querySelector(`[name="${name}"]`).value;

  preview.style.background = get('bg_primary');
  preview.style.color = get('text_primary');

  const accent = document.getElementById('pvAccent');
  if (accent) accent.style.color = get('accent');

  const cta = document.getElementById('pvCta');
  if (cta) {
    cta.style.background = get('cta');
    cta.style.color = get('cta_text');
  }

  const body = document.getElementById('pvBody');
  if (body) body.style.color = get('text_secondary');

  const tagline = document.getElementById('pvTagline');
  if (tagline) {
    tagline.style.color = get('text_muted');
    const tag = get('tagline') || get('display_name') || get('brand_name');
    if (tag) tagline.textContent = tag;
  }

  const footer = document.getElementById('pvFooter');
  if (footer) {
    footer.style.borderColor = get('bg_secondary');
    footer.style.color = get('text_muted');
    footer.textContent = get('display_name') || get('brand_name') || 'brand';
  }

  // Font preview (load from Google Fonts)
  const heading = get('font_heading');
  const bodyFont = get('font_body');
  loadFont(heading);
  loadFont(bodyFont);
  document.getElementById('pvHeadline').style.fontFamily = `'${heading}', sans-serif`;
  document.getElementById('pvBody').style.fontFamily = `'${bodyFont}', sans-serif`;

  const weight = get('heading_weight_heavy') || '700';
  document.getElementById('pvHeadline').style.fontWeight = weight;
}

const loadedFonts = new Set();
function loadFont(name) {
  if (loadedFonts.has(name)) return;
  loadedFonts.add(name);
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${name.replace(/ /g, '+')}:wght@400;500;600;700;800;900&display=swap`;
  document.head.appendChild(link);
}

// Attach listeners to all inputs
form.querySelectorAll('input, select').forEach(el => {
  el.addEventListener('input', updatePreview);
  el.addEventListener('change', updatePreview);
});

// Initial preview
updatePreview();
