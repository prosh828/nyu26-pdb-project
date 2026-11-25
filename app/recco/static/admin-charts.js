// Small SVG charts for the admin statistics page (templates/admin/stats.html).
// Each <div class="chart" data-kind="column|bar" data-points='[{label, value, ...}]'>
// is drawn to its container's width and redrawn on resize. Every bar has a hover /
// keyboard-focus tooltip; the same numbers are in the table under each chart.
// Text is set with textContent only (titles can contain any characters).
(function () {
  var SVG = "http://www.w3.org/2000/svg";
  var CHAR_W = 6.2;               // approximate width of one 11px label character

  function el(name, attrs, parent) {
    var node = document.createElementNS(SVG, name);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function text(parent, x, y, str, attrs) {
    var t = el("text", Object.assign({ x: x, y: y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }

  function fmt(value, format) {
    if (format === "score") return value.toFixed(2);
    return Math.round(value).toLocaleString("en-US");
  }

  function axisFmt(value, max) {
    if (value === 0) return "0";
    if (max >= 10000) return (value / 1000).toLocaleString("en-US") + "K";
    return value.toLocaleString("en-US");
  }

  // A "nice" axis maximum and step (1, 2, 2.5 or 5 x 10^n), about 4 gridlines.
  function niceScale(max, format) {
    if (format === "score") return { max: 5, step: 1 };
    if (max <= 0) return { max: 1, step: 1 };
    var raw = max / 4, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var step = [1, 2, 2.5, 5, 10].map(function (m) { return m * mag; })
      .filter(function (s) { return s >= raw; })[0];
    if (step < 1) step = 1;
    return { max: Math.ceil(max / step) * step, step: step };
  }

  // Bar with a 4px rounded data end and a square baseline end.
  function columnPath(x, y, w, h) {
    var r = Math.min(4, w / 2, h);
    return "M" + x + "," + (y + h) + "V" + (y + r) + "Q" + x + "," + y + " " + (x + r) + "," + y +
      "H" + (x + w - r) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + r) + "V" + (y + h) + "Z";
  }

  function barPath(x, y, w, h) {
    var r = Math.min(4, h / 2, w);
    return "M" + x + "," + y + "H" + (x + w - r) + "Q" + (x + w) + "," + y + " " + (x + w) + "," + (y + r) +
      "V" + (y + h - r) + "Q" + (x + w) + "," + (y + h) + " " + (x + w - r) + "," + (y + h) + "H" + x + "Z";
  }

  function truncate(str, chars) {
    return str.length > chars ? str.slice(0, chars - 1) + "…" : str;
  }

  // --- tooltip ----------------------------------------------------------------
  function tooltipFor(box) {
    var tip = box.querySelector(".tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "tooltip";
      tip.hidden = true;
      box.appendChild(tip);
    }
    return tip;
  }

  function attachTip(box, hit, point, opts) {
    function show() {
      var tip = tooltipFor(box);
      tip.textContent = "";
      var strong = document.createElement("strong");
      strong.textContent = fmt(point.value, opts.format) + " " + opts.valueName.toLowerCase();
      tip.appendChild(strong);
      tip.appendChild(document.createTextNode(point.label));
      if (opts.extraKey && point[opts.extraKey] != null) {
        tip.appendChild(document.createElement("br"));
        tip.appendChild(document.createTextNode(fmt(point[opts.extraKey], "int") + " " + opts.extraName.toLowerCase()));
      }
      tip.hidden = false;
      var b = hit.getBBox(), svg = hit.ownerSVGElement, scale = svg.clientWidth / svg.viewBox.baseVal.width;
      var left = (b.x + b.width / 2) * scale - tip.offsetWidth / 2;
      left = Math.max(0, Math.min(left, box.clientWidth - tip.offsetWidth));
      var top = (opts.kind === "bar" ? b.y + b.height + 4 : opts.tipY) * scale;
      tip.style.left = left + "px";
      tip.style.top = top + "px";
    }
    function hide() { tooltipFor(box).hidden = true; }
    hit.addEventListener("pointerenter", show);
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", show);
    hit.addEventListener("blur", hide);
  }

  // --- column chart (vertical) ---------------------------------------------------
  function drawColumns(box, points, opts) {
    var W = box.clientWidth, H = 220, m = { top: 20, right: 6, bottom: 24, left: 0 };
    var values = points.map(function (p) { return p.value; });
    var maxV = Math.max.apply(null, values), scale = niceScale(maxV, opts.format);
    m.left = Math.max(28, axisFmt(scale.max, scale.max).length * CHAR_W + 10);
    var pw = W - m.left - m.right, ph = H - m.top - m.bottom, band = pw / points.length;
    var bw = Math.max(2, Math.min(24, band - 2));          // 2px surface gap between touching bars
    var y = function (v) { return m.top + ph - (v / scale.max) * ph; };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H });

    for (var t = 0; t <= scale.max + 1e-9; t += scale.step) {
      el("line", { x1: m.left, x2: W - m.right, y1: y(t), y2: y(t), class: t === 0 ? "baseline" : "gridline" }, svg);
      text(svg, m.left - 6, y(t) + 4, axisFmt(t, scale.max), { "text-anchor": "end" });
    }
    var longest = Math.max.apply(null, points.map(function (p) { return p.label.length; }));
    var every = Math.max(1, Math.ceil((longest * CHAR_W + 8) / band));
    var maxIndex = values.indexOf(maxV);
    points.forEach(function (p, i) {
      var cx = m.left + band * (i + 0.5), x = cx - bw / 2, h = y(0) - y(p.value);
      var hit = el("rect", { x: m.left + band * i, y: m.top, width: band, height: ph, class: "hit", tabindex: 0,
                             "aria-label": p.label + ": " + fmt(p.value, opts.format) }, svg);
      if (h > 0) {
        el("path", { d: columnPath(x, y(p.value), bw, h),
                     class: "mark" + (opts.highlightFrom != null && i >= opts.highlightFrom ? " hl" : "") }, svg);
      }
      if (i % every === 0) text(svg, cx, H - 8, p.label, { "text-anchor": "middle" });
      if (i === maxIndex) text(svg, cx, y(p.value) - 6, fmt(p.value, opts.format), { "text-anchor": "middle", class: "value" });
      attachTip(box, hit, p, Object.assign({ kind: "column", tipY: m.top }, opts));
    });
    return svg;
  }

  // --- bar chart (horizontal, ranked) ---------------------------------------------
  function drawBars(box, points, opts) {
    var W = box.clientWidth, row = 26, bh = 14, m = { top: 4, right: 0, bottom: 4, left: 0 };
    var maxChars = Math.max(8, Math.floor(W * 0.38 / CHAR_W));
    var labels = points.map(function (p) { return truncate(p.label, maxChars); });
    m.left = Math.max.apply(null, labels.map(function (l) { return l.length; })) * CHAR_W + 10;
    var maxV = Math.max.apply(null, points.map(function (p) { return p.value; }));
    var scale = niceScale(maxV, opts.format);
    m.right = fmt(maxV, opts.format).length * CHAR_W + 10;  // room for the value at the tip
    var H = m.top + m.bottom + row * points.length, pw = W - m.left - m.right;
    var x = function (v) { return m.left + (v / scale.max) * pw; };
    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H });
    el("line", { x1: m.left, x2: m.left, y1: m.top, y2: H - m.bottom, class: "baseline" }, svg);
    points.forEach(function (p, i) {
      var top = m.top + row * i, by = top + (row - bh) / 2, w = x(p.value) - m.left;
      var hit = el("rect", { x: 0, y: top, width: W, height: row, class: "hit", tabindex: 0,
                             "aria-label": p.label + ": " + fmt(p.value, opts.format) }, svg);
      if (w > 0) el("path", { d: barPath(m.left, by, w, bh), class: "mark" }, svg);
      text(svg, m.left - 8, top + row / 2 + 4, labels[i], { "text-anchor": "end", class: "cat" });
      text(svg, m.left + w + 6, top + row / 2 + 4, fmt(p.value, opts.format), { class: "value" });
      attachTip(box, hit, p, Object.assign({ kind: "bar" }, opts));
    });
    return svg;
  }

  function draw(box) {
    var points = JSON.parse(box.dataset.points);
    var opts = {
      format: box.dataset.format || "int",
      valueName: box.dataset.valueName || "Count",
      extraKey: box.dataset.extraKey, extraName: box.dataset.extraName || "",
      highlightFrom: box.dataset.highlightFrom != null ? Number(box.dataset.highlightFrom) : null
    };
    var svg = (box.dataset.kind === "bar" ? drawBars : drawColumns)(box, points, opts);
    box.querySelectorAll("svg").forEach(function (old) { old.remove(); });
    box.insertBefore(svg, box.firstChild);
  }

  var charts = document.querySelectorAll(".chart[data-points]");
  charts.forEach(draw);
  if (window.ResizeObserver) {
    var widths = new WeakMap();
    var ro = new ResizeObserver(function (entries) {
      entries.forEach(function (e) {
        var w = Math.round(e.contentRect.width);
        if (widths.get(e.target) !== w) { widths.set(e.target, w); draw(e.target); }
      });
    });
    charts.forEach(function (c) { widths.set(c, c.clientWidth); ro.observe(c); });
  }
})();
