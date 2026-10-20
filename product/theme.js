// Light/dark toggle. Writes the same localStorage key and values as the Docusaurus docs, so the choice carries over.
(function () {
  var root = document.documentElement;
  var button = document.querySelector('.theme-toggle');
  var meta = document.querySelector('meta[name="theme-color"]');

  // Runs after every theme change: relabel the toggle, and keep Safari's toolbar tint (theme-color) on the page color,
  // since Safari does not resample the page when the theme changes.
  function label() {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    button.setAttribute('aria-label', 'Switch to ' + next + ' mode');
    meta.setAttribute('content', getComputedStyle(root).getPropertyValue('--paper').trim());
  }

  button.addEventListener('click', function () {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('theme', next); } catch (e) {}
    label();
  });

  // Follow the system setting until the reader picks a mode.
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (event) {
    var stored = null;
    try { stored = localStorage.getItem('theme'); } catch (e) {}
    if (!stored) {
      root.setAttribute('data-theme', event.matches ? 'dark' : 'light');
      label();
    }
  });

  label();
})();
