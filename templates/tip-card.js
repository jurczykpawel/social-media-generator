initTemplate(function (ctx) {
  var params = ctx.params, brandName = ctx.brandName;
  document.getElementById('footerName').textContent = brandName;

  var badge = params.get('badge');
  var title = params.get('title');
  var bullets = params.get('bullets');
  var num = params.get('num');

  if (badge) document.getElementById('badge').textContent = badge;
  if (title) document.getElementById('title').textContent = title;
  if (num) document.getElementById('seriesNum').textContent = '#' + num;

  if (bullets) {
    var list = document.getElementById('bullets');
    while (list.firstChild) list.removeChild(list.firstChild);
    bullets.split('|').forEach(function (text) {
      var li = document.createElement('li');
      li.className = 'bullet';
      var icon = document.createElement('div');
      icon.className = 'bullet-icon';
      var span = document.createElement('span');
      span.className = 'bullet-text';
      span.textContent = text.trim();
      li.appendChild(icon);
      li.appendChild(span);
      list.appendChild(li);
    });
  }

  autoSizeText(document.getElementById('title'), [
    [30, 5], [60, 4.2], [100, 3.5], [Infinity, 2.8]
  ]);

  var vw = window.innerWidth / 100;
  var bulletSize = Math.max(2 * vw, 16);
  document.querySelectorAll('.bullet-text').forEach(function (b) {
    b.style.fontSize = bulletSize + 'px';
  });
});
