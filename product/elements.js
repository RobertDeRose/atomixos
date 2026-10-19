// Periodic table: picking an element shows its note in the element card. Without JavaScript the card stays hidden
// and the full list of notes below the table is shown instead.
(function () {
  var card = document.querySelector('.element-card');
  var notes = document.querySelector('.notes');
  var tiles = document.querySelectorAll('.ptable .el');
  if (!card || !notes || !tiles.length) return;

  function show(tile) {
    var note = document.getElementById(tile.getAttribute('data-note'));
    if (!note) return;
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

  tiles.forEach(function (tile) {
    tile.addEventListener('click', function () {
      show(tile);
      // On narrow screens the card sits above the table; bring it into view.
      if (card.getBoundingClientRect().top < 0) card.scrollIntoView({block: 'nearest'});
    });
  });

  notes.hidden = true;
  card.hidden = false;
  show(document.querySelector('.ptable .el[data-note="el-ct"]') || tiles[0]);
})();
