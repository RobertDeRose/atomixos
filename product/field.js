// Background field of free electrons, drawn on a fixed canvas behind the page. Scrolling fires them along their own
// headings at depth-scaled speeds, each trailing a streak that grows with scroll speed and fades as the page settles.
// Nothing moves while the page is still. Reduced-motion readers get the same field without the motion.
(function () {
  var SPEED = 3.2; // field travel per pixel scrolled, for the nearest electrons
  var STREAK = 9; // streak length in frames of travel
  var MAX_STREAK = 260; // longest streak, in pixels
  var EASE = 0.2; // how quickly the field catches up with the scroll position; lower glides longer

  var canvas = document.querySelector('.field');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var electrons = [];
  var width = 0;
  var height = 0;
  var color = '28, 100, 209';
  var core = '255, 255, 255';
  var glow = 0.6;
  var shown = window.scrollY; // eased scroll position the field is drawn at
  var frame = null;

  function readColors() {
    var style = getComputedStyle(document.documentElement);
    color = style.getPropertyValue('--electron-rgb').trim() || color;
    core = style.getPropertyValue('--electron-core-rgb').trim() || core;
    glow = parseFloat(style.getPropertyValue('--electron-glow')) || glow;
  }

  // A fixed-seed generator keeps the field identical between visits and resizes.
  function random(seed) {
    return function () {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
  }

  function populate() {
    var next = random(42);
    var count = Math.round(Math.min(110, Math.max(36, (width * height) / 18000)));
    electrons = [];
    for (var i = 0; i < count; i++) {
      var depth = 0.2 + next() * 0.8; // 1 is nearest: bigger, brighter, faster
      // Mostly against the scroll direction, fanned out up to 35 degrees either side.
      var angle = (next() - 0.5) * 1.2;
      electrons.push({
        x: next(),
        y: next(),
        depth: depth,
        radius: 0.7 + depth * 1.5,
        dx: Math.sin(angle),
        dy: -Math.cos(angle),
      });
    }
  }

  function resize() {
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    populate();
    draw(shown, 0);
  }

  function wrap(value, span) {
    value %= span;
    return value < 0 ? value + span : value;
  }

  // velocity is the eased scroll change in this frame; it sets streak length and brightness.
  function draw(scroll, velocity) {
    ctx.clearRect(0, 0, width, height);
    var margin = MAX_STREAK;
    var spanX = width + margin * 2;
    var spanY = height + margin * 2;
    electrons.forEach(function (e) {
      var travel = scroll * e.depth * SPEED;
      var x = wrap(e.x * spanX + e.dx * travel, spanX) - margin;
      var y = wrap(e.y * spanY + e.dy * travel, spanY) - margin;
      var alpha = (0.35 + e.depth * 0.6) * glow;

      var length = Math.min(MAX_STREAK, Math.abs(velocity) * e.depth * SPEED * STREAK);
      if (length > 2) {
        // The streak trails behind the electron's direction of travel.
        var sign = velocity > 0 ? 1 : -1;
        var tx = x - e.dx * sign * length;
        var ty = y - e.dy * sign * length;
        var streak = ctx.createLinearGradient(x, y, tx, ty);
        streak.addColorStop(0, 'rgba(' + color + ', ' + alpha + ')');
        streak.addColorStop(1, 'rgba(' + color + ', 0)');
        ctx.strokeStyle = streak;
        ctx.lineWidth = e.radius * 1.4;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(tx, ty);
        ctx.stroke();
      }

      var halo = ctx.createRadialGradient(x, y, 0, x, y, e.radius * 3);
      halo.addColorStop(0, 'rgba(' + color + ', ' + alpha + ')');
      halo.addColorStop(1, 'rgba(' + color + ', 0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(x, y, e.radius * 3, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = 'rgba(' + color + ', ' + Math.min(1, alpha * 1.4) + ')';
      ctx.beginPath();
      ctx.arc(x, y, e.radius, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = 'rgba(' + core + ', ' + Math.min(1, alpha * 1.6) + ')';
      ctx.beginPath();
      ctx.arc(x, y, e.radius * 0.45, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Ease toward the real scroll position so the field keeps a little momentum, then stop drawing until the next scroll.
  function tick() {
    var target = window.scrollY;
    var previous = shown;
    shown += (target - shown) * EASE;
    if (Math.abs(target - shown) < 0.3) shown = target;
    draw(shown, shown - previous);
    frame = shown === target ? null : requestAnimationFrame(tick);
    // One last frame with no velocity clears the streaks once the field settles.
    if (frame === null) draw(shown, 0);
  }

  function onScroll() {
    if (reducedMotion) return;
    if (frame === null) frame = requestAnimationFrame(tick);
  }

  readColors();
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('scroll', onScroll, {passive: true});
  // The theme toggle switches data-theme on <html>; redraw in the new colors.
  new MutationObserver(function () {
    readColors();
    draw(shown, 0);
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
})();
