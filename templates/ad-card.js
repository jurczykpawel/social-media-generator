initTemplate(function (ctx) {
  var params = ctx.params, brandName = ctx.brandName;
  document.getElementById('footerName').textContent = brandName;

  var badge = params.get('badge');
  var title = params.get('title');
  var text = params.get('text');
  var cta = params.get('cta');
  var urgency = params.get('urgency');
  var attr = params.get('attr');

  if (badge) document.getElementById('badge').textContent = badge;
  else document.getElementById('badge').style.display = 'none';

  if (title) {
    var headlineEl = document.getElementById('headline');
    headlineEl.textContent = '';
    var parts = title.split(/\*(.*?)\*/g);
    for (var i = 0; i < parts.length; i++) {
      if (i % 2 === 0) {
        headlineEl.appendChild(document.createTextNode(parts[i]));
      } else {
        var em = document.createElement('em');
        em.textContent = parts[i];
        headlineEl.appendChild(em);
      }
    }
  }

  if (text) document.getElementById('valueProp').textContent = text;
  else document.getElementById('valueProp').style.display = 'none';

  if (cta) document.getElementById('cta').textContent = cta;
  else document.getElementById('cta').style.display = 'none';

  if (urgency) document.getElementById('urgency').textContent = urgency;
  else document.getElementById('urgency').style.display = 'none';

  if (attr) document.getElementById('subtext').textContent = attr;
  else document.getElementById('subtext').style.display = 'none';

  autoSizeText(document.getElementById('headline'), [
    [25, 6], [45, 5], [70, 4.2], [100, 3.5], [Infinity, 2.8]
  ], 0.3);
});
