/* FluBNF sandbox model views (model-views.js)

   Draws the two model views of the sandbox from the graph JSON the
   console's routes return beside their SVG: the reaction network (each
   species a box, each reaction an arrow from what it consumes to what it
   makes with the rate law written on the arrow, a dashed line from a
   catalyst to the arrow's middle, a dot for a source or a sink) and the
   contact map in RuleBender's style (a panel per molecule type with a
   header strip, component boxes inside, state ellipses under their
   component, bonds as arcs between component boxes).

   Both are view only: nothing here edits the model. The viewer pans by
   dragging the background, zooms with the wheel or the + - reset buttons,
   drags any node or molecule (edges, labels and bonds follow), hovers a
   node to see its own edges alone, clicks it to keep that, clicks the
   background to let it go. A status line under the drawing names what
   the pointer is on.

   The network's layout is a seeded force layout: the nodes start on a
   ring in their own order, then repulsion between nodes, springs along
   the edges and a gentle pull to the centre settle them over ITER
   rounds. The seed is fixed, so the same model draws the same way on
   every load. Colours are the page's tokens through model-views.css, so
   the drawing follows the theme with no redraw. Plain ES5, no
   dependencies. ModelViews.network(box, graph) and
   ModelViews.contactmap(box, graph) return the view built for the box
   ({el, reset}); ModelViews.layout is exported for tests. */
(function (root) {
  'use strict';
  var SVG = 'http://www.w3.org/2000/svg';
  var HEIGHT = 420;              // the drawing's height in px; its width is the card's
  var CHAR = 7.2, PAD = 8;       // px per character at the 12 px label size, and around it
  var NODE_H = 24, DOT_R = 5;    // a species box; a source or sink dot
  var MARGIN = 36;               // kept clear inside the drawing's edge
  var ITER = 300, SEED = 20240907;
  var BEND = 30;                 // between parallel arrows on one pair of species
  // the contact map's panels, the same measures as the server's drawing
  var HEAD = 26, COMP_H = 22, STATE_H = 18, GAP = 22, PPAD = 10;
  var BOND_RISE = 64, BOND_ROOM = 26;

  // ------------------------------------------------------------- helpers
  function el(tag, attrs, parent) {
    var e = document.createElementNS(SVG, tag), k;
    for (k in attrs) if (attrs.hasOwnProperty(k)) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function text(parent, x, y, s, attrs) {
    var t = el('text', attrs || {}, parent);
    t.setAttribute('x', x);
    t.setAttribute('y', y);
    t.textContent = s;
    return t;
  }
  function html(tag, cls, parent) {
    var e = document.createElement(tag);
    e.className = cls;
    if (parent) parent.appendChild(e);
    return e;
  }
  function has(e, cls) {
    var c = e.getAttribute && e.getAttribute('class');
    return !!c && (' ' + c + ' ').indexOf(' ' + cls + ' ') >= 0;
  }
  // the nearest element carrying cls, from target up to (not including) stop
  function up(target, cls, stop) {
    var e = target;
    while (e && e !== stop) {
      if (has(e, cls)) return e;
      e = e.parentNode;
    }
    return null;
  }
  function mark(e, base, mod) { e.setAttribute('class', mod ? base + ' ' + mod : base); }
  function width(s, min) { return Math.max(min || 36, CHAR * String(s).length + 2 * PAD); }
  function join(list, sep) { return list.join(sep || ', '); }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : many); }
  // a small deterministic generator (a linear congruence), for the ring's jitter
  function seeded(seed) {
    var s = seed >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) % 4294967296;
      return s / 4294967296;
    };
  }
  // where a ray from a box's centre towards (dx, dy) leaves the box, plus a hair
  function rim(p, dx, dy, w, h) {
    var d = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / d, uy = dy / d;
    var tx = Math.abs(ux) > 1e-6 ? (w / 2) / Math.abs(ux) : Infinity;
    var ty = Math.abs(uy) > 1e-6 ? (h / 2) / Math.abs(uy) : Infinity;
    var t = Math.min(tx, ty) + 2;
    return {x: p.x + ux * t, y: p.y + uy * t};
  }

  // ---------------------------------------------------------- the view
  // The frame both drawings share: the SVG with its viewBox, the zoom
  // buttons, the status line, and the pointer: drag on the background
  // pans, drag on something draggable moves it, the wheel zooms about
  // the pointer, hover and click go to the drawing's own handlers.
  function View(box, w, h) {
    var self = this;
    this.el = html('div', 'mv');
    this.svg = el('svg', {'class': 'mv-svg', preserveAspectRatio: 'xMidYMid meet', role: 'img'}, this.el);
    this.home = {x: 0, y: 0, w: w, h: h};
    this.vb = {x: 0, y: 0, w: w, h: h};
    this.tools = html('div', 'mv-tools', this.el);
    this.status = html('p', 'mv-status', this.el);
    this.idle = '';
    this.pinned = null;
    this.drag = null;
    // the drawing's handlers, replaced by each drawing
    this.pick = function () { return null; };          // the thing under an element, or null
    this.movable = function () { return null; };       // the id a drag moves, or null
    this.moveTo = function () {};                      // (id, x, y) after a drag
    this.startOf = function () { return {x: 0, y: 0}; }; // (id) where a drag starts
    this.paint = function () {};                       // (hit or null) the highlight
    this.describe = function () { return ''; };        // (hit) the status line
    this.onReset = function () {};
    this.apply();
    this.button('+', 'zoom in', function () { self.zoom(1 / 1.25); });
    this.button('-', 'zoom out', function () { self.zoom(1.25); });
    this.button('reset', 'reset the view', function () { self.reset(); });
    this.wire();
  }
  View.prototype.button = function (label, title, fn) {
    var b = html('button', 'mv-btn', this.tools);
    b.type = 'button';
    b.textContent = label;
    b.title = title;
    b.setAttribute('aria-label', title);
    b.addEventListener('click', fn);
  };
  View.prototype.apply = function () {
    var v = this.vb;
    this.svg.setAttribute('viewBox', v.x + ' ' + v.y + ' ' + v.w + ' ' + v.h);
  };
  View.prototype.setHome = function (w, h) {
    this.home = {x: 0, y: 0, w: w, h: h};
    this.vb = {x: 0, y: 0, w: w, h: h};
    this.apply();
  };
  View.prototype.say = function (s) { this.status.textContent = s || this.idle; };
  // user units per screen pixel (the viewBox meets the box, so the larger ratio)
  View.prototype.scale = function () {
    var cw = this.svg.clientWidth || this.vb.w, ch = this.svg.clientHeight || this.vb.h;
    return Math.max(this.vb.w / cw, this.vb.h / ch);
  };
  View.prototype.point = function (ev) {
    var m = this.svg.getScreenCTM && this.svg.getScreenCTM(), pt;
    if (!m || !this.svg.createSVGPoint) return {x: 0, y: 0};
    pt = this.svg.createSVGPoint();
    pt.x = ev.clientX;
    pt.y = ev.clientY;
    pt = pt.matrixTransform(m.inverse());
    return {x: pt.x, y: pt.y};
  };
  // zoom by f (below 1 zooms in) about a user point, the centre by default
  View.prototype.zoom = function (f, cx, cy) {
    var v = this.vb, w = v.w * f;
    if (w < this.home.w / 8 || w > this.home.w * 6) return;
    if (cx === undefined) { cx = v.x + v.w / 2; cy = v.y + v.h / 2; }
    v.x = cx - (cx - v.x) * f;
    v.y = cy - (cy - v.y) * f;
    v.w = w;
    v.h = v.h * f;
    this.apply();
  };
  View.prototype.reset = function () {
    this.vb = {x: this.home.x, y: this.home.y, w: this.home.w, h: this.home.h};
    this.apply();
    this.pinned = null;
    this.paint(null);
    this.say('');
    this.onReset();
  };
  View.prototype.wire = function () {
    var self = this, svg = this.svg;
    function move(ev) {
      var d = self.drag, p;
      if (!d) return;
      if (!d.moved && Math.abs(ev.clientX - d.x0) + Math.abs(ev.clientY - d.y0) < 3) return;
      d.moved = true;
      if (d.id !== null) {
        p = self.point(ev);
        self.moveTo(d.id, d.start.x + p.x - d.p0.x, d.start.y + p.y - d.p0.y);
      } else {
        self.vb.x = d.vb0.x - (ev.clientX - d.x0) * d.scale;
        self.vb.y = d.vb0.y - (ev.clientY - d.y0) * d.scale;
        self.apply();
      }
    }
    function end() {
      var d = self.drag;
      document.removeEventListener('mousemove', move);
      document.removeEventListener('mouseup', end);
      if (!d) return;
      self.drag = null;
      mark(svg, 'mv-svg', '');
      if (d.moved) return;
      // a click: pin what was clicked, or let a pin go on the background
      if (d.hit) self.pinned = (self.pinned && self.pinned.key === d.hit.key) ? null : d.hit;
      else self.pinned = null;
      self.paint(self.pinned || d.hit);
      self.say(d.hit ? self.describe(d.hit) : '');
    }
    svg.addEventListener('mousedown', function (ev) {
      var hit, id;
      if (ev.button !== 0) return;
      ev.preventDefault();
      hit = self.pick(ev.target);
      id = hit ? self.movable(hit) : null;
      self.drag = {hit: hit, id: id, x0: ev.clientX, y0: ev.clientY, p0: self.point(ev),
                   start: id !== null ? self.startOf(id) : null,
                   vb0: {x: self.vb.x, y: self.vb.y}, scale: self.scale(), moved: false};
      if (id === null) mark(svg, 'mv-svg', 'mv-panning');
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', end);
    });
    svg.addEventListener('mouseover', function (ev) {
      var hit = self.pick(ev.target);
      if (self.drag) return;
      self.say(hit ? self.describe(hit) : '');
      if (!self.pinned) self.paint(hit);
    });
    svg.addEventListener('mouseleave', function () {
      if (self.drag) return;
      self.say('');
      if (!self.pinned) self.paint(null);
    });
    svg.addEventListener('wheel', function (ev) {
      var p = self.point(ev);
      ev.preventDefault();
      self.zoom(ev.deltaY > 0 ? 1.15 : 1 / 1.15, p.x, p.y);
    }, {passive: false});
  };

  // --------------------------------------------------- the force layout
  // Nodes start on a ring in their own order (a hair of seeded jitter so
  // no two forces cancel exactly), then ITER rounds of repulsion between
  // every pair (fading out past 1.5 k, gone at 2.5 k), springs along the
  // edges (source and sink dots pulled in closer, influences weakly
  // towards both ends of their arrow) and a gentle pull to the centre,
  // with a cooling cap on each move. The result is then scaled to fill
  // the drawing, MARGIN kept clear.
  function layout(graph, W, H) {
    var nodes = graph.nodes || [], n = nodes.length, pos = {}, size = {}, idx = {};
    var rnd = seeded(SEED), cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.4;
    var springs = [], i, j, it, a, e, f, k, temp, disp, p, q, dx, dy, d, force, s;
    for (i = 0; i < n; i++) {
      a = -Math.PI / 2 + 2 * Math.PI * i / Math.max(n, 1);
      idx[nodes[i].id] = i;
      pos[nodes[i].id] = {x: cx + R * Math.cos(a) + rnd() - 0.5, y: cy + R * Math.sin(a) + rnd() - 0.5};
      size[nodes[i].id] = nodes[i].kind === 'species'
        ? {w: width(nodes[i].label), h: NODE_H} : {w: 2 * DOT_R, h: 2 * DOT_R};
    }
    for (i = 0; i < (graph.edges || []).length; i++) {
      e = graph.edges[i];
      if (e.from === e.to || idx[e.from] === undefined || idx[e.to] === undefined) continue;
      springs.push([e.from, e.to, (e.kind === 'source' || e.kind === 'sink') ? 2 : 1]);
    }
    for (i = 0; i < (graph.influences || []).length; i++) {
      f = graph.influences[i];
      for (j = 0; j < (graph.edges || []).length; j++) {
        e = graph.edges[j];
        if (e.id !== f.edge || idx[f.from] === undefined) continue;
        if (idx[e.from] !== undefined && e.from !== f.from) springs.push([f.from, e.from, 0.3]);
        if (idx[e.to] !== undefined && e.to !== f.from) springs.push([f.from, e.to, 0.3]);
      }
    }
    k = Math.min(Math.sqrt(W * H / (n + 1)) * 0.9, 150);
    for (it = 0; it < ITER; it++) {
      temp = Math.max(W, H) / 8 * (1 - it / ITER) + 0.5;
      disp = {};
      for (i = 0; i < n; i++) disp[nodes[i].id] = {x: 0, y: 0};
      for (i = 0; i < n; i++) {
        p = pos[nodes[i].id];
        for (j = i + 1; j < n; j++) {
          q = pos[nodes[j].id];
          dx = p.x - q.x; dy = p.y - q.y;
          d = Math.sqrt(dx * dx + dy * dy) || 0.01;
          // repulsion fades out past 1.5 k and is gone at 2.5 k, so a
          // part of the network no edge joins to the rest is not pushed
          // off the drawing
          force = k * k / d * Math.max(0, Math.min(1, 2.5 - d / k));
          disp[nodes[i].id].x += dx / d * force; disp[nodes[i].id].y += dy / d * force;
          disp[nodes[j].id].x -= dx / d * force; disp[nodes[j].id].y -= dy / d * force;
        }
        // the pull to the centre
        disp[nodes[i].id].x -= (p.x - cx) * 0.08;
        disp[nodes[i].id].y -= (p.y - cy) * 0.08;
      }
      for (i = 0; i < springs.length; i++) {
        s = springs[i];
        p = pos[s[0]]; q = pos[s[1]];
        dx = p.x - q.x; dy = p.y - q.y;
        d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        force = d * d / k * s[2];
        disp[s[0]].x -= dx / d * force; disp[s[0]].y -= dy / d * force;
        disp[s[1]].x += dx / d * force; disp[s[1]].y += dy / d * force;
      }
      for (i = 0; i < n; i++) {
        p = pos[nodes[i].id]; q = disp[nodes[i].id];
        d = Math.sqrt(q.x * q.x + q.y * q.y) || 0.01;
        s = Math.min(d, temp) / d;
        p.x += q.x * s; p.y += q.y * s;
      }
    }
    fit(pos, size, W, H);
    return pos;
  }
  function fit(pos, size, W, H) {
    var ids = Object.keys(pos), x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    var i, p, s, sw, sh, ox, oy;
    if (!ids.length) return;
    for (i = 0; i < ids.length; i++) {
      p = pos[ids[i]]; s = size[ids[i]];
      x0 = Math.min(x0, p.x - s.w / 2); x1 = Math.max(x1, p.x + s.w / 2);
      y0 = Math.min(y0, p.y - s.h / 2); y1 = Math.max(y1, p.y + s.h / 2);
    }
    sw = (x1 - x0) || 1; sh = (y1 - y0) || 1;
    s = Math.min((W - 2 * MARGIN) / sw, (H - 2 * MARGIN) / sh, 1.4);
    ox = (W - sw * s) / 2 - x0 * s; oy = (H - sh * s) / 2 - y0 * s;
    for (i = 0; i < ids.length; i++) {
      p = pos[ids[i]];
      p.x = Math.round(p.x * s + ox); p.y = Math.round(p.y * s + oy);
    }
  }

  // ------------------------------------------------ the reaction network
  function network(box, graph) {
    var W = Math.max(320, box.clientWidth || 640), H = HEIGHT;
    var v = new View(box, W, H), svg = v.svg;
    var nodes = graph.nodes || [], edges = graph.edges || [], infs = graph.influences || [];
    var defs = el('defs', {}, svg), gInf, gEdges, gHits, gLabels, gNodes;
    var pos = layout(graph, W, H), home = {}, size = {}, N = {}, E = {}, I = [], pairs = {};
    var species = 0, reactions = {}, i, key, list, o;
    ['mv-arrow', 'mv-arrow-mut'].forEach(function (id) {
      var m = el('marker', {id: id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7,
                            markerHeight: 7, orient: 'auto'}, defs);
      el('path', {d: 'M0,0 L10,5 L0,10 z', 'class': id}, m);
    });
    gInf = el('g', {}, svg); gEdges = el('g', {}, svg); gHits = el('g', {}, svg);
    gLabels = el('g', {}, svg); gNodes = el('g', {}, svg);
    nodes.forEach(function (nd) {
      var base = 'mv-node mv-' + nd.kind, g = el('g', {'class': base, 'data-id': nd.id}, gNodes), w;
      if (nd.kind === 'species') {
        w = width(nd.label);
        species += 1;
        el('rect', {x: -w / 2, y: -NODE_H / 2, width: w, height: NODE_H, rx: 6}, g);
        text(g, 0, 4, nd.label, {'text-anchor': 'middle'});
        size[nd.id] = {w: w, h: NODE_H};
      } else {
        el('circle', {r: DOT_R}, g);
        size[nd.id] = {w: 2 * DOT_R, h: 2 * DOT_R};
      }
      home[nd.id] = {x: pos[nd.id].x, y: pos[nd.id].y};
      N[nd.id] = {node: nd, g: g, base: base, edges: [], infs: []};
    });
    // arrows on one pair of species each get their own bend, in one frame
    // for both directions so none of them lands on another
    edges.forEach(function (e) {
      if (!N[e.from] || !N[e.to]) return;
      key = e.from < e.to ? e.from + '|' + e.to : e.to + '|' + e.from;
      (pairs[key] = pairs[key] || []).push(e);
    });
    for (key in pairs) if (pairs.hasOwnProperty(key)) {
      list = pairs[key];
      for (i = 0; i < list.length; i++) {
        o = (i - (list.length - 1) / 2) * BEND;
        list[i].bend = list[i].from <= list[i].to ? o : -o;
      }
    }
    edges.forEach(function (e) {
      var dot = e.kind === 'source' || e.kind === 'sink', base = 'mv-edge mv-' + e.kind;
      if (!N[e.from] || !N[e.to]) return;
      reactions[e.rule || e.id] = 1;
      E[e.id] = {
        edge: e, base: base, infs: [], mid: null,
        path: el('path', {'class': base, 'data-edge': e.id,
                          'marker-end': 'url(#' + (dot ? 'mv-arrow-mut' : 'mv-arrow') + ')'}, gEdges),
        hit: el('path', {'class': 'mv-hit', 'data-edge': e.id}, gHits),
        label: text(gLabels, 0, 0, e.label, {'class': 'mv-label', 'data-edge': e.id, 'text-anchor': 'middle'})
      };
      N[e.from].edges.push(e.id);
      if (e.to !== e.from) N[e.to].edges.push(e.id);
    });
    infs.forEach(function (f) {
      var rec;
      if (!N[f.from] || !E[f.edge]) return;
      rec = {inf: f, path: el('path', {'class': 'mv-inf'}, gInf), dot: el('circle', {'class': 'mv-inf-dot', r: 3}, gInf)};
      I.push(rec);
      N[f.from].infs.push(rec);
      E[f.edge].infs.push(rec);
    });
    v.idle = plural(species, 'species', 'species') + ', ' + plural(Object.keys(reactions).length, 'reaction', 'reactions');
    svg.setAttribute('aria-label', 'reaction network: ' + v.idle);

    // an arrow's path: a loop over its one node, a line, or a bent curve;
    // both ends stop at the boxes' rims, the label sits at the middle
    function geometry(e) {
      var pa = pos[e.from], pb = pos[e.to], sa = size[e.from], sb = size[e.to];
      var top, dx, dy, d, nx, ny, cx, cy, a, b;
      if (e.from === e.to) {
        top = pa.y - sa.h / 2;
        return {d: 'M' + (pa.x - 8) + ',' + top + ' C' + (pa.x - 36) + ',' + (top - 48) + ' '
                  + (pa.x + 36) + ',' + (top - 48) + ' ' + (pa.x + 8) + ',' + top,
                x: pa.x, y: top - 36};
      }
      dx = pb.x - pa.x; dy = pb.y - pa.y;
      d = Math.sqrt(dx * dx + dy * dy) || 1;
      nx = -dy / d; ny = dx / d;
      cx = (pa.x + pb.x) / 2 + nx * (e.bend || 0);
      cy = (pa.y + pb.y) / 2 + ny * (e.bend || 0);
      a = rim(pa, cx - pa.x, cy - pa.y, sa.w, sa.h);
      b = rim(pb, cx - pb.x, cy - pb.y, sb.w, sb.h);
      if (!e.bend) return {d: 'M' + a.x + ',' + a.y + ' L' + b.x + ',' + b.y, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
      return {d: 'M' + a.x + ',' + a.y + ' Q' + cx + ',' + cy + ' ' + b.x + ',' + b.y,
              x: 0.25 * a.x + 0.5 * cx + 0.25 * b.x, y: 0.25 * a.y + 0.5 * cy + 0.25 * b.y};
    }
    // an influence: a dashed arc from the species to the arrow's middle,
    // bowing out further when the species is one of the arrow's own ends
    // (a straight line would lie on the arrow)
    function influence(rec) {
      var p = pos[rec.inf.from], s = size[rec.inf.from], e = E[rec.inf.edge], m = e.mid;
      var own = e.edge.from === rec.inf.from || e.edge.to === rec.inf.from;
      var dx = m.x - p.x, dy = m.y - p.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      var bow = d * (own ? 0.5 : 0.25), cx = (p.x + m.x) / 2 - dy / d * bow, cy = (p.y + m.y) / 2 + dx / d * bow;
      var a = rim(p, cx - p.x, cy - p.y, s.w, s.h);
      rec.path.setAttribute('d', 'M' + a.x + ',' + a.y + ' Q' + cx + ',' + cy + ' ' + m.x + ',' + m.y);
      rec.dot.setAttribute('cx', m.x);
      rec.dot.setAttribute('cy', m.y);
    }
    function place() {
      Object.keys(N).forEach(function (id) {
        N[id].g.setAttribute('transform', 'translate(' + pos[id].x + ' ' + pos[id].y + ')');
      });
      Object.keys(E).forEach(function (id) {
        var r = E[id], g = geometry(r.edge);
        r.path.setAttribute('d', g.d);
        r.hit.setAttribute('d', g.d);
        r.label.setAttribute('x', g.x);
        r.label.setAttribute('y', g.y + 4);
        r.mid = g;
      });
      I.forEach(influence);
    }
    // the highlight: a node keeps its arrows, their far ends and its
    // influences; an arrow keeps its ends and its influences; the rest dims
    function paint(hit) {
      var keepN = {}, keepE = {}, keepI = [], r, e;
      function keepEdge(id) {
        var rec = E[id];
        keepE[id] = 1;
        keepN[rec.edge.from] = 1;
        keepN[rec.edge.to] = 1;
        rec.infs.forEach(function (x) { keepI.push(x); keepN[x.inf.from] = 1; });
      }
      if (hit && hit.kind === 'node' && N[hit.id]) {
        keepN[hit.id] = 1;
        N[hit.id].edges.forEach(keepEdge);
        N[hit.id].infs.forEach(function (x) { keepEdge(x.inf.edge); });
      } else if (hit && hit.kind === 'edge' && E[hit.id]) {
        keepEdge(hit.id);
      } else {
        hit = null;
      }
      for (r in N) if (N.hasOwnProperty(r)) mark(N[r].g, N[r].base, !hit ? '' : keepN[r] ? 'mv-hi' : 'mv-dim');
      for (r in E) if (E.hasOwnProperty(r)) {
        e = E[r];
        mark(e.path, e.base, !hit ? '' : keepE[r] ? 'mv-hi' : 'mv-dim');
        mark(e.label, 'mv-label', !hit ? '' : keepE[r] ? 'mv-hi' : 'mv-dim');
      }
      I.forEach(function (x) {
        var m = !hit ? '' : keepI.indexOf(x) >= 0 ? 'mv-hi' : 'mv-dim';
        mark(x.path, 'mv-inf', m);
        mark(x.dot, 'mv-inf-dot', m);
      });
    }
    v.pick = function (t) {
      var g = up(t, 'mv-node', svg), e = t && t.getAttribute && t.getAttribute('data-edge');
      if (g) return {kind: 'node', id: g.getAttribute('data-id'), key: 'n:' + g.getAttribute('data-id')};
      if (e) return {kind: 'edge', id: e, key: 'e:' + e};
      return null;
    };
    v.movable = function (hit) { return hit.kind === 'node' && N[hit.id] ? hit.id : null; };
    v.startOf = function (id) { return {x: pos[id].x, y: pos[id].y}; };
    v.moveTo = function (id, x, y) { pos[id].x = x; pos[id].y = y; place(); };
    v.describe = function (hit) {
      if (hit.kind === 'node' && N[hit.id]) return N[hit.id].node.text || N[hit.id].node.label;
      if (hit.kind === 'edge' && E[hit.id]) return E[hit.id].edge.text || E[hit.id].edge.label;
      return '';
    };
    v.paint = paint;
    v.onReset = function () {
      Object.keys(home).forEach(function (id) { pos[id].x = home[id].x; pos[id].y = home[id].y; });
      place();
    };
    place();
    v.say('');
    return v;
  }

  // ------------------------------------------------------ the contact map
  function contactmap(box, graph) {
    var W = Math.max(320, box.clientWidth || 640), H = HEIGHT;
    var v = new View(box, W, H), svg = v.svg;
    var mols = graph.molecules || [], bonds = graph.bonds || [];
    var gMols = el('g', {}, svg), gBonds = el('g', {}, svg);
    var P = {}, C = {}, B = [], home = {};
    var x = 0, y = bonds.length ? BOND_ROOM : 0, rowH = 0, dw = 0, vw, vh, ox, oy, ncomp = 0;
    // the panels fill rows across the drawing, GAP apart, as the server lays them
    mols.forEach(function (m) {
      var comps = m.components || [], cells = [], hasStates = false, w, h;
      comps.forEach(function (c) {
        var states = c.states || [], sw = 0;
        states.forEach(function (s) { sw += width(s, 24); });
        sw += 4 * Math.max(states.length - 1, 0);
        cells.push(Math.max(width(c.name, 30), sw));
        if (states.length) hasStates = true;
      });
      w = Math.max(width(m.name, 70), cells.reduce(function (a, b) { return a + b; }, 0)
                   + 8 * Math.max(cells.length - 1, 0) + 2 * PPAD);
      h = HEAD + (comps.length ? 8 + COMP_H + (hasStates ? 4 + STATE_H : 0) + 8 : 0);
      if (x > 0 && x + w > W - 2) { x = 0; y += rowH + GAP; rowH = 0; }
      P[m.id] = {mol: m, x: x, y: y, w: w, h: h, cells: cells};
      rowH = Math.max(rowH, h);
      dw = Math.max(dw, x + w);
      x += w + GAP;
    });
    // a larger map than the drawing widens the home view; a smaller one sits centred
    vw = Math.max(W, dw + 2 * MARGIN);
    vh = Math.max(H, y + rowH + 2 * MARGIN);
    ox = Math.round((vw - dw) / 2);
    oy = Math.round((vh - (y + rowH)) / 2);
    v.setHome(vw, vh);
    mols.forEach(function (m) {
      var p = P[m.id], g = el('g', {'class': 'mv-mol', 'data-id': m.id}, gMols);
      var comps = m.components || [], cx = PPAD, cy = HEAD + 8;
      p.x += ox; p.y += oy;
      p.g = g;
      home[m.id] = {x: p.x, y: p.y};
      el('rect', {x: 0, y: 0, width: p.w, height: p.h, rx: 8, 'class': 'mv-ground'}, g);
      if (comps.length) {
        el('rect', {x: 0, y: 0, width: p.w, height: HEAD + 8, rx: 8, 'class': 'mv-head'}, g);
        el('rect', {x: 0, y: HEAD, width: p.w, height: p.h - HEAD - 8, 'class': 'mv-ground'}, g);
      } else {
        el('rect', {x: 0, y: 0, width: p.w, height: p.h, rx: 8, 'class': 'mv-head'}, g);
      }
      el('rect', {x: 0, y: 0, width: p.w, height: p.h, rx: 8, 'class': 'mv-panel'}, g);
      text(g, p.w / 2, 17.5, m.name, {'text-anchor': 'middle', 'class': 'mv-mol-name'});
      comps.forEach(function (c, ci) {
        var cw = p.cells[ci], cg = el('g', {'class': 'mv-comp', 'data-id': c.id}, g);
        var states = c.states || [], widths = [], sx, ey;
        ncomp += 1;
        el('rect', {x: cx, y: cy, width: cw, height: COMP_H, rx: 4}, cg);
        text(cg, cx + cw / 2, cy + 15, c.name, {'text-anchor': 'middle'});
        C[c.id] = {comp: c, mol: m, g: cg, lx: cx + cw / 2, ly: cy, bonds: []};
        states.forEach(function (s) { widths.push(width(s, 24)); });
        sx = cx + (cw - (widths.reduce(function (a, b) { return a + b; }, 0) + 4 * Math.max(widths.length - 1, 0))) / 2;
        ey = cy + COMP_H + 4;
        states.forEach(function (s, si) {
          var sw = widths[si], sg = el('g', {'class': 'mv-state', 'data-comp': c.id, 'data-state': s}, g);
          el('ellipse', {cx: sx + sw / 2, cy: ey + STATE_H / 2, rx: sw / 2, ry: STATE_H / 2}, sg);
          text(sg, sx + sw / 2, ey + 13, s, {'text-anchor': 'middle'});
          sx += sw + 4;
        });
        cx += cw + 8;
      });
    });
    bonds.forEach(function (b, bi) {
      if (!C[b.from] || !C[b.to]) return;
      B.push({bond: b, i: bi, path: el('path', {'class': 'mv-bond', 'data-bond': bi}, gBonds)});
      C[b.from].bonds.push(B[B.length - 1]);
      C[b.to].bonds.push(B[B.length - 1]);
    });
    v.idle = plural(mols.length, 'molecule type', 'molecule types') + ', '
      + (B.length ? plural(B.length, 'bond', 'bonds') : 'no bonds');
    svg.setAttribute('aria-label', 'contact map: ' + v.idle);

    function at(cid) { var c = C[cid], p = P[c.mol.id]; return {x: p.x + c.lx, y: p.y + c.ly, top: p.y}; }
    function name(cid) { return C[cid].mol.name + '.' + C[cid].comp.name; }
    function place() {
      Object.keys(P).forEach(function (id) {
        P[id].g.setAttribute('transform', 'translate(' + P[id].x + ' ' + P[id].y + ')');
      });
      B.forEach(function (r) {
        var a = at(r.bond.from), b = at(r.bond.to), top = Math.min(a.top, b.top);
        r.path.setAttribute('d', 'M' + a.x + ',' + a.y + ' Q' + (a.x + b.x) / 2 + ',' + (top - BOND_RISE) + ' ' + b.x + ',' + b.y);
      });
    }
    // the highlight: a component keeps its bonds and their far components;
    // a bond keeps its two components; the other bonds dim
    function paint(hit) {
      var keepC = {}, keepB = [];
      if (hit && hit.kind === 'comp' && C[hit.id]) {
        keepC[hit.id] = 1;
        C[hit.id].bonds.forEach(function (r) { keepB.push(r); keepC[r.bond.from] = 1; keepC[r.bond.to] = 1; });
      } else if (hit && hit.kind === 'bond' && B[hit.id]) {
        keepB.push(B[hit.id]);
        keepC[B[hit.id].bond.from] = 1;
        keepC[B[hit.id].bond.to] = 1;
      } else {
        hit = null;
      }
      Object.keys(C).forEach(function (id) { mark(C[id].g, 'mv-comp', hit && keepC[id] ? 'mv-hi' : ''); });
      B.forEach(function (r) { mark(r.path, 'mv-bond', !hit ? '' : keepB.indexOf(r) >= 0 ? 'mv-hi' : 'mv-dim'); });
    }
    v.pick = function (t) {
      var c = up(t, 'mv-comp', svg), s = up(t, 'mv-state', svg), m = up(t, 'mv-mol', svg);
      var b = t && t.getAttribute && t.getAttribute('data-bond');
      if (c) return {kind: 'comp', id: c.getAttribute('data-id'), key: 'c:' + c.getAttribute('data-id')};
      if (s) return {kind: 'state', id: s.getAttribute('data-comp'), state: s.getAttribute('data-state'),
                     key: 's:' + s.getAttribute('data-comp') + ':' + s.getAttribute('data-state')};
      if (b) return {kind: 'bond', id: +b, key: 'b:' + b};
      if (m) return {kind: 'mol', id: m.getAttribute('data-id'), key: 'm:' + m.getAttribute('data-id')};
      return null;
    };
    v.movable = function (hit) {
      if (hit.kind === 'mol' && P[hit.id]) return hit.id;
      if ((hit.kind === 'comp' || hit.kind === 'state') && C[hit.id]) return C[hit.id].mol.id;
      return null;
    };
    v.startOf = function (id) { return {x: P[id].x, y: P[id].y}; };
    v.moveTo = function (id, x, y) { P[id].x = x; P[id].y = y; place(); };
    v.describe = function (hit) {
      var c, m, partners;
      if (hit.kind === 'comp' && C[hit.id]) {
        c = C[hit.id];
        partners = c.bonds.map(function (r) { return name(r.bond.from === hit.id ? r.bond.to : r.bond.from); });
        return 'component ' + c.comp.name + ' of ' + c.mol.name
          + (c.comp.states && c.comp.states.length ? ', states ' + join(c.comp.states) : '')
          + (partners.length ? ', binds ' + join(partners) : ', no bonds');
      }
      if (hit.kind === 'state' && C[hit.id]) return 'state ' + hit.state + ' of ' + name(hit.id);
      if (hit.kind === 'bond' && B[hit.id]) return 'bond ' + name(B[hit.id].bond.from) + ' to ' + name(B[hit.id].bond.to);
      if (hit.kind === 'mol' && P[hit.id]) {
        m = P[hit.id].mol;
        return 'molecule type ' + m.name + (m.components && m.components.length
          ? ': components ' + join(m.components.map(function (c) { return c.name; })) : ', no components');
      }
      return '';
    };
    v.paint = paint;
    v.onReset = function () {
      Object.keys(home).forEach(function (id) { P[id].x = home[id].x; P[id].y = home[id].y; });
      place();
    };
    place();
    v.say('');
    return v;
  }

  root.ModelViews = {network: network, contactmap: contactmap, layout: layout};
})(typeof window !== 'undefined' ? window : this);
