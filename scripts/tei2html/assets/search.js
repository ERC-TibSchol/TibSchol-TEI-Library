// Site search: the Pagefind UI opens in an overlay from the header button (or with the / key).
// The index is built by build_site.py (npx pagefind --site <site>); without it the overlay stays empty.
(function () {
  var button = document.querySelector('.search-open');
  if (!button) return;

  var overlay = document.createElement('div');
  overlay.className = 'search-overlay';
  overlay.setAttribute('data-pagefind-ignore', 'data-pagefind-ignore');
  overlay.hidden = true;
  overlay.innerHTML = '<div class="search-dialog" role="dialog" aria-modal="true" aria-label="Search the excerpts">' +
    '<button type="button" class="search-close" aria-label="Close search">&times;</button>' +
    '<div class="search-panel"></div></div>';
  document.body.appendChild(overlay);

  var panel = overlay.querySelector('.search-panel');
  var ui = null;

  function show() {
    overlay.hidden = false;
    if (!ui && window.PagefindUI) {
      ui = new PagefindUI({
        element: panel,
        showSubResults: true,
        showImages: false,
        translations: { placeholder: 'Search the excerpts' }
      });
    }
    var input = panel.querySelector('input');
    if (input) input.focus();
  }

  function hide() {
    overlay.hidden = true;
    button.focus();
  }

  button.addEventListener('click', show);
  overlay.querySelector('.search-close').addEventListener('click', hide);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) hide(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !overlay.hidden) hide();
    var typing = /input|textarea|select/i.test(document.activeElement.tagName);
    if (e.key === '/' && overlay.hidden && !typing) { e.preventDefault(); show(); }
  });
})();
