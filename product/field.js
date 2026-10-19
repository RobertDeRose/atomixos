// Background field of free electrons, drawn on a fixed canvas behind the page. Scrolling moves them: each electron
// drifts at its own depth-based speed, sways sideways, and leaves a short trail while the page is moving. The field is
// still when the page is. Reduced-motion readers get the same field without the motion.
(function () {
  var canvas = document.querySelector('.field');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var electrons = [];
  var width = 0;
  var height = 0;
  var ratio = 1;
  var color = '28, 100, 209';
  var glow = 0.5;
  var shown = window.scrollY; // eased scroll position the field is drawn at
  var frame = null;

  function readColors() {
    var style = getComputedStyle(document.documentElement);
    color = style.getPropertyValue('--electron-rgb').trim() || color;
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
    var count = Math.round(Math.min(140, Math.max(40, (width * height) / 16000)));
    electrons = [];
    for (var i = 0; i < count; i++) {
      var depth = 0.15 + next() * 0.85; // 1 is nearest: bigger, brighter, faster
      electrons.push({
        x: next(),
        y: next(),
        depth: depth,
        radius: 0.8 + depth * 2.4,
        sway: 6 + next() * 28,
        phase: next() * Math.PI * 2,
        tempo: 0.6 + next() * 1.4,
      });
    }
  }

  function resize() {
    ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    populate();
    draw(shown, shown);
  }

  function position(e, scroll) {
    var span = height + 80;
    var y = (e.y * span - scroll * e.depth * 0.6) % span;
    if (y < 0) y += span;
    var x = e.x * width + Math.sin(scroll * 0.004 * e.tempo + e.phase) * e.sway * e.depth;
    return {x: x, y: y - 40};
  }

  function draw(scroll, previous) {
    ctx.clearRect(0, 0, width, height);
    var moving = Math.abs(scroll - previous) > 0.5;
    electrons.forEach(function (e) {
      var p = position(e, scroll);
      var alpha = (0.18 + e.depth * 0.5) * glow;
      if (moving && !reducedMotion) {
        var q = position(e, previous);
        // Skip the trail when the electron wrapped around the screen edge.
        if (Math.abs(q.y - p.y) < height / 2) {
          ctx.strokeStyle = 'rgba(' + color + ', ' + alpha * 0.45 + ')';
          ctx.lineWidth = e.radius * 0.9;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(q.x, q.y);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
        }
      }
      var halo = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, e.radius * 4);
      halo.addColorStop(0, 'rgba(' + color + ', ' + alpha + ')');
      halo.addColorStop(0.3, 'rgba(' + color + ', ' + alpha * 0.5 + ')');
      halo.addColorStop(1, 'rgba(' + color + ', 0)');
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(p.x, p.y, e.radius * 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Ease toward the real scroll position so the field glides, then stop drawing until the next scroll.
  function tick() {
    var target = window.scrollY;
    var previous = shown;
    shown += (target - shown) * 0.12;
    if (Math.abs(target - shown) < 0.5) shown = target;
    draw(shown, previous);
    frame = shown === target ? null : requestAnimationFrame(tick);
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
    draw(shown, shown);
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
})();
