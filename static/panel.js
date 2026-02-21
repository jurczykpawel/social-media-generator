// Panel — external script (no inline JS for CSP compliance)

document.addEventListener('DOMContentLoaded', function () {
  // Copy token button
  var copyBtn = document.getElementById('copyTokenBtn');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      fetch('/panel/token/copy')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          navigator.clipboard.writeText(data.token).then(function () {
            copyBtn.textContent = 'Copied!';
            setTimeout(function () { copyBtn.textContent = 'Copy full token'; }, 1500);
          });
        });
    });
  }

  // Regenerate token confirm
  var regenForm = document.getElementById('regenTokenForm');
  if (regenForm) {
    regenForm.addEventListener('submit', function (e) {
      if (!confirm('Regenerate token? The old one will stop working.')) {
        e.preventDefault();
      }
    });
  }

  // Brand delete confirms
  document.querySelectorAll('.brand-delete-form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      var name = form.getAttribute('data-brand');
      if (!confirm('Delete brand ' + name + '?')) {
        e.preventDefault();
      }
    });
  });
});
