// Periodic table: the element card shows one element's note. Without JavaScript the card stays hidden and the full
// list of notes below the table is shown instead.
//
// The card cycles through the elements while the table is on screen. Hovering or focusing a tile previews it and
// pauses the cycle; clicking a tile pins it and stops the cycle for good. Reduced-motion readers get no cycle.
(function () {
  var CYCLE_MS = 4000;
  var card = document.querySelector('.element-card');
  var notes = document.querySelector('.notes');
  var table = document.querySelector('.ptable');
  var tiles = Array.prototype.slice.call(document.querySelectorAll('.ptable .el'));
  if (!card || !notes || !table || !tiles.length) return;

  var current = 0;
  var pinned = null;
  var paused = false;
  var visible = false;
  var timer = null;
  var reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(index) {
    var tile = tiles[index];
    var note = document.getElementById(tile.getAttribute('data-note'));
    if (!note) return;
    current = index;
    tiles.forEach(function (other) { other.setAttribute('aria-pressed', String(other === tile)); });
    card.className = 'element-card ' + note.className.replace('note ', '').replace('note--', 'element-card--');
    card.querySelector('.element-card__num').textContent = note.getAttribute('data-num');
    card.querySelector('.element-card__sym').textContent = note.getAttribute('data-sym');
    card.querySelector('.element-card__mass').textContent = note.getAttribute('data-mass');
    card.querySelector('.element-card__family').textContent = note.getAttribute('data-family');
    card.querySelector('.element-card__name').textContent = note.querySelector('dt').textContent;
    // The note text is static page content, so its inline code markup is copied as-is.
    card.querySelector('.element-card__text').innerHTML = note.querySelector('dd').innerHTML;
  }

  // Automatic changes are not announced; only a reader's own pick is.
  function announce(on) {
    card.setAttribute('aria-live', on ? 'polite' : 'off');
  }

  function schedule() {
    clearInterval(timer);
    timer = null;
    if (reducedMotion || pinned !== null || paused || !visible || document.hidden) return;
    timer = setInterval(function () {
      announce(false);
      show((current + 1) % tiles.length);
    }, CYCLE_MS);
  }

  tiles.forEach(function (tile, index) {
    tile.addEventListener('click', function () {
      pinned = index;
      announce(true);
      show(index);
      schedule();
      // On narrow screens the card sits above the table; bring it into view.
      if (card.getBoundingClientRect().top < 0) card.scrollIntoView({block: 'nearest'});
    });
    tile.addEventListener('mouseenter', function () { if (pinned === null) show(index); });
    tile.addEventListener('focus', function () { if (pinned === null) { announce(true); show(index); } });
  });

  // Pause while the pointer or keyboard focus is anywhere on the table or the card.
  [table, card].forEach(function (area) {
    area.addEventListener('mouseenter', function () { paused = true; schedule(); });
    area.addEventListener('mouseleave', function () { paused = false; schedule(); });
    area.addEventListener('focusin', function () { paused = true; schedule(); });
    area.addEventListener('focusout', function () { paused = false; schedule(); });
  });

  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      visible = entries[0].isIntersecting;
      schedule();
    }, {threshold: 0.3}).observe(table);
  } else {
    visible = true;
  }
  document.addEventListener('visibilitychange', schedule);

  notes.hidden = true;
  card.hidden = false;
  announce(false);
  var start = tiles.findIndex(function (tile) { return tile.getAttribute('data-note') === 'el-ct'; });
  show(start < 0 ? 0 : start);
  schedule();
})();
