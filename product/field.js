// Background field of free electrons, drawn on a fixed canvas behind the page. Scrolling fires them along their own
// headings at depth-scaled speeds, each trailing a streak that grows with scroll speed and fades as the page settles.
// Headings wobble, speeds change with every flick, and electrons that leave the screen re-enter somewhere new, so the
// field never replays. Nothing moves while the page is still. Reduced-motion readers get a still field.
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

  // The first paint uses a fixed seed so the page always loads the same; motion after that is random.
  function random(seed) {
    return function () {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };
  }

  // Headings fan out up to 35 degrees either side of straight up (the scroll direction moves them along it).
  var FAN = 0.6;

  function spawn(e, next) {
    e.depth = 0.2 + next() * 0.8; // 1 is nearest: bigger, brighter, faster
    e.radius = 0.7 + e.depth * 1.5;
    e.base = (next() - 0.5) * 2 * FAN;
    e.angle = e.base;
    e.speed = 0.7 + next() * 0.6;
    return e;
  }

  function populate() {
    var next = random(42);
    var count = Math.round(Math.min(110, Math.max(36, (width * height) / 18000)));
    electrons = [];
    for (var i = 0; i < count; i++) {
      var e = spawn({}, next);
      e.x = next() * width;
      e.y = next() * height;
      electrons.push(e);
    }
  }

  // Each flick gets its own mix of speeds.
  function reroll() {
    electrons.forEach(function (e) {
      e.speed = 0.7 + Math.random() * 0.6;
    });
  }

  function resize() {
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    populate();
    draw(0);
  }

  // Move every electron by this frame's eased scroll change; one that leaves the screen re-enters from the opposite
  // edge at a random spot with a fresh depth, heading, and speed.
  function step(velocity) {
    var margin = MAX_STREAK;
    electrons.forEach(function (e) {
      // A small random wobble, stronger at speed, kept within the fan.
      e.angle += (Math.random() - 0.5) * Math.min(0.12, Math.abs(velocity) * 0.004);
      e.angle = Math.max(e.base - 0.25, Math.min(e.base + 0.25, e.angle));
      var travel = velocity * e.depth * e.speed * SPEED;
      e.x += Math.sin(e.angle) * travel;
      e.y -= Math.cos(e.angle) * travel;
      var out = e.y < -margin || e.y > height + margin || e.x < -margin || e.x > width + margin;
      if (!out) return;
      var fromBelow = e.y < -margin;
      spawn(e, Math.random);
      e.x = Math.random() * width;
      e.y = fromBelow ? height + margin * Math.random() : -margin * Math.random();
    });
  }

  // velocity is the eased scroll change in this frame; it sets streak length.
  function draw(velocity) {
    ctx.clearRect(0, 0, width, height);
    electrons.forEach(function (e) {
      var x = e.x;
      var y = e.y;
      var dx = Math.sin(e.angle);
      var dy = -Math.cos(e.angle);
      var alpha = (0.35 + e.depth * 0.6) * glow;

      var length = Math.min(MAX_STREAK, Math.abs(velocity) * e.depth * e.speed * SPEED * STREAK);
      if (length > 2) {
        // The streak trails behind the electron's direction of travel.
        var sign = velocity > 0 ? 1 : -1;
        var tx = x - dx * sign * length;
        var ty = y - dy * sign * length;
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
    var velocity = shown - previous;
    step(velocity);
    draw(velocity);
    frame = shown === target ? null : requestAnimationFrame(tick);
    // One last frame with no velocity clears the streaks once the field settles.
    if (frame === null) draw(0);
  }

  function onScroll() {
    if (reducedMotion) return;
    if (frame === null) {
      reroll();
      frame = requestAnimationFrame(tick);
    }
  }

  readColors();
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('scroll', onScroll, {passive: true});
  // The theme toggle switches data-theme on <html>; redraw in the new colors.
  new MutationObserver(function () {
    readColors();
    draw(0);
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
})();
