/**
 * Shared base logic for all templates.
 *
 * Usage in template:
 *   <script src="_base.js"></script>
 *   <script>
 *     initTemplate(({ params, styles, brandName }) => {
 *       // template-specific content population here
 *     });
 *   </script>
 */

function initTemplate(callback) {
  const params = new URLSearchParams(window.location.search);

  // Load brand CSS
  const brand = params.get('brand') || 'example';
  let brandsDir = params.get('brands_dir') ||
    window.location.pathname.replace(/\/templates\/.*$/, '') + '/brands';
  // Only allow safe relative paths (block arbitrary URLs, protocol-relative URLs, and path traversal)
  if (window.location.protocol !== 'file:') {
    if (brandsDir.indexOf('://') !== -1 || brandsDir.indexOf('..') !== -1 ||
        brandsDir.indexOf('//') === 0) {
      brandsDir = '/preview/brands';
    }
  }
  const cssLink = document.getElementById('brand-css');
  cssLink.href = brandsDir + '/' + brand + '.css';

  cssLink.addEventListener('load', () => {
    const styles = getComputedStyle(document.documentElement);
    const brandName = styles.getPropertyValue('--brand-name').trim().replace(/"/g, '');

    // Background image (optional)
    const bg = params.get('bg');
    if (bg) {
      const bgEl = document.createElement('div');
      bgEl.className = 'bg-image';
      bgEl.style.backgroundImage = 'url("file://' + bg + '")';
      document.body.insertBefore(bgEl, document.body.firstChild);

      const overlayEl = document.createElement('div');
      overlayEl.className = 'bg-overlay';
      overlayEl.style.opacity = params.get('bg_opacity') || '0.65';
      bgEl.after(overlayEl);
    }

    // Call template-specific setup
    callback({ params, styles, brandName });
  });
}

/**
 * Auto-size a text element to fit within maxHeightRatio of viewport.
 * @param {HTMLElement} el - Element to resize
 * @param {Array} breakpoints - [[maxChars, vwMultiplier], ...] sorted by maxChars ascending
 * @param {number} maxHeightRatio - Max fraction of viewport height (default 0.35)
 */
function autoSizeText(el, breakpoints, maxHeightRatio) {
  maxHeightRatio = maxHeightRatio || 0.35;
  const len = el.textContent.length;
  const vw = window.innerWidth / 100;

  let size = breakpoints[breakpoints.length - 1][1] * vw;
  for (let i = 0; i < breakpoints.length; i++) {
    if (len < breakpoints[i][0]) {
      size = breakpoints[i][1] * vw;
      break;
    }
  }
  el.style.fontSize = size + 'px';

  const maxHeight = window.innerHeight * maxHeightRatio;
  while (el.scrollHeight > maxHeight && size > 1.8 * vw) {
    size -= 0.5;
    el.style.fontSize = size + 'px';
  }
}
