initTemplate(function (ctx) {
  var params = ctx.params, styles = ctx.styles, brandName = ctx.brandName;
  var brandTagline = styles.getPropertyValue('--brand-tagline').trim().replace(/"/g, '');

  document.getElementById('footerName').textContent = brandName;
  document.getElementById('tagline').textContent = brandTagline;

  var text = params.get('text');
  var attr = params.get('attr');
  var num = params.get('num');

  if (text) document.getElementById('quoteText').textContent = text;
  if (attr) document.getElementById('attrText').textContent = '— ' + attr;
  if (num) document.getElementById('seriesNum').textContent = '#' + num;

  autoSizeText(document.getElementById('quoteText'), [
    [40, 5.5], [80, 4.8], [120, 4.2], [180, 3.6], [250, 3.0], [Infinity, 2.6]
  ], 0.5);
});
