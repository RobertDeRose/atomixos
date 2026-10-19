// Light/dark toggle. Writes the same localStorage key and values as the Docusaurus docs, so the choice carries over.
(function () {
  var root = document.documentElement;
  var button = document.querySelector('.theme-toggle');

  function label() {
    var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    button.setAttribute('aria-label', 'Switch to ' + next + ' mode');
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
