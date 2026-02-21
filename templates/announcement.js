initTemplate(function (ctx) {
  var params = ctx.params, brandName = ctx.brandName;
  document.getElementById('footerName').textContent = brandName;

  var badge = params.get('badge');
  var title = params.get('title');
  var attr = params.get('attr');
  var date = params.get('date');
  var cta = params.get('cta');

  if (badge) document.getElementById('badge').textContent = badge;
  if (title) document.getElementById('title').textContent = title;
  if (attr) document.getElementById('speaker').textContent = attr;
  if (date) document.getElementById('date').textContent = date;
  if (cta) document.getElementById('cta').textContent = cta;

  if (!attr) document.getElementById('speaker').style.display = 'none';
  if (!date) document.getElementById('date').style.display = 'none';
  if (!cta) document.getElementById('cta').style.display = 'none';

  autoSizeText(document.getElementById('title'), [
    [30, 5.5], [60, 4.5], [100, 3.8], [Infinity, 3]
  ], 0.35);
});
