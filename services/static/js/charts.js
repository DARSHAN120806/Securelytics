/* Tiny dependency-free SVG charts for the Securelytics dashboard.
   Solid theme colours only (read from CSS variables), hover tooltips, responsive. */
(function () {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const color = (c) => (c && c.startsWith("--") ? css(c) : c);
  const esc = (s) => String(s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));

  function svg(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  function niceMax(v) {
    if (!isFinite(v) || v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }

  function setup(el, height) {
    el.innerHTML = "";
    el.classList.add("chart");
    const w = Math.max(el.clientWidth, 240);
    const root = svg("svg", { viewBox: `0 0 ${w} ${height}`, height, role: "img" }, el);
    const tip = document.createElement("div");
    tip.className = "tip hidden";
    el.appendChild(tip);
    return { w, h: height, root, tip };
  }

  function showTip(tip, x, y, html) {
    tip.innerHTML = html;
    tip.style.left = x + "px";
    tip.style.top = y + "px";
    tip.classList.remove("hidden");
  }

  const registry = new Set();
  function remember(el, fn) {
    el._render = fn;
    registry.add(el);
    fn();
  }
  let rt;
  window.addEventListener("resize", () => {
    clearTimeout(rt);
    rt = setTimeout(() => registry.forEach((el) => (document.body.contains(el) ? el._render() : registry.delete(el))), 120);
  });

  /* ---------------- line chart ---------------- */
  function line(el, o) {
    remember(el, () => {
      const H = o.height || 240, pad = { l: 44, r: 14, t: 12, b: 28 };
      const { w, root, tip } = setup(el, H);
      const n = o.labels.length;
      const max = niceMax(Math.max(1, ...o.series.flatMap((s) => s.values)));
      const X = (i) => pad.l + (n <= 1 ? 0 : (i * (w - pad.l - pad.r)) / (n - 1));
      const Y = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b);
      for (let k = 0; k <= 4; k++) {
        const v = (max * k) / 4, y = Y(v);
        svg("line", { x1: pad.l, x2: w - pad.r, y1: y, y2: y, class: "grid-line" }, root);
        const t = svg("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", class: "axis-label" }, root);
        t.textContent = (o.yFormat || fmtShort)(v);
      }
      const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor((w - 60) / 70))));
      o.labels.forEach((lab, i) => {
        if (i % step && i !== n - 1) return;
        if (i === n - 1 && i % step && (i % step) < step * 0.6) return; // avoid overlapping the previous label
        const t = svg("text", { x: X(i), y: H - 8, "text-anchor": "middle", class: "axis-label" }, root);
        t.textContent = o.xFormat ? o.xFormat(lab) : lab;
      });
      o.series.forEach((s) => {
        const c = color(s.color);
        if (s.bars) {
          const bw = Math.max(2, Math.min(10, (w - pad.l - pad.r) / n - 3));
          s.values.forEach((v, i) => {
            if (!v) return;
            svg("rect", { x: X(i) - bw / 2, y: Y(v), width: bw, height: Math.max(1, H - pad.b - Y(v)), rx: 2, fill: c, opacity: 0.9 }, root);
          });
        } else {
          const d = s.values.map((v, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join("");
          svg("path", { d, fill: "none", stroke: c, "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round" }, root);
        }
      });
      const guide = svg("line", { y1: pad.t, y2: H - pad.b, stroke: css("--faint"), "stroke-dasharray": "3 4", opacity: 0 }, root);
      const dots = o.series.map((s) => svg("circle", { r: 4.5, fill: color(s.color), stroke: css("--bg"), "stroke-width": 2, opacity: 0 }, root));
      const hit = svg("rect", { x: pad.l, y: pad.t, width: w - pad.l - pad.r, height: H - pad.t - pad.b, fill: "transparent" }, root);
      hit.addEventListener("mousemove", (e) => {
        const r = root.getBoundingClientRect();
        const px = ((e.clientX - r.left) / r.width) * w;
        const i = Math.max(0, Math.min(n - 1, Math.round(((px - pad.l) / (w - pad.l - pad.r)) * (n - 1))));
        guide.setAttribute("x1", X(i)); guide.setAttribute("x2", X(i)); guide.setAttribute("opacity", 1);
        o.series.forEach((s, k) => { dots[k].setAttribute("cx", X(i)); dots[k].setAttribute("cy", Y(s.values[i])); dots[k].setAttribute("opacity", 1); });
        const html = `<b>${esc(o.xFormat ? o.xFormat(o.labels[i], true) : o.labels[i])}</b><br>` +
          o.series.map((s) => `<i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${color(s.color)}"></i> ${esc(s.name)}: <b>${(o.tipFormat || fmtInt)(s.values[i])}</b>`).join("<br>");
        showTip(tip, (X(i) / w) * r.width, (Math.min(...o.series.map((s) => Y(s.values[i]))) / H) * r.height, html);
      });
      hit.addEventListener("mouseleave", () => { guide.setAttribute("opacity", 0); dots.forEach((d) => d.setAttribute("opacity", 0)); tip.classList.add("hidden"); });
    });
  }

  /* ---------------- donut ---------------- */
  function donut(el, o) {
    remember(el, () => {
      el.innerHTML = "";
      const size = o.size || 180, r = size / 2 - 14, cx = size / 2, cy = size / 2, sw = 22;
      const total = o.items.reduce((a, b) => a + b.value, 0);
      const wrap = document.createElement("div");
      wrap.className = "donut-wrap";
      el.appendChild(wrap);
      const holder = document.createElement("div");
      holder.className = "chart";
      holder.style.width = size + "px";
      wrap.appendChild(holder);
      const root = svg("svg", { viewBox: `0 0 ${size} ${size}`, width: size, height: size }, holder);
      const tip = document.createElement("div"); tip.className = "tip hidden"; holder.appendChild(tip);
      svg("circle", { cx, cy, r, fill: "none", stroke: css("--line"), "stroke-width": sw }, root);
      const C = 2 * Math.PI * r;
      let acc = 0;
      o.items.forEach((it) => {
        if (!it.value) return;
        const frac = it.value / (total || 1);
        // visible gap between segments, but keep tiny segments visible
        const len = Math.max(frac * C - 3, 7);
        const seg = svg("circle", {
          cx, cy, r, fill: "none", stroke: color(it.color), "stroke-width": sw,
          "stroke-dasharray": `${len} ${C - len}`, "stroke-dashoffset": -acc * C, transform: `rotate(-90 ${cx} ${cy})`,
          "stroke-linecap": "butt", style: "cursor:pointer",
        }, root);
        acc += frac;
        seg.addEventListener("mousemove", (e) => {
          const b = holder.getBoundingClientRect();
          showTip(tip, e.clientX - b.left, e.clientY - b.top, `${esc(it.label)}: <b>${fmtInt(it.value)}</b> (${(frac * 100).toFixed(frac < 0.01 ? 2 : 1)}%)`);
        });
        seg.addEventListener("mouseleave", () => tip.classList.add("hidden"));
      });
      const t1 = svg("text", { x: cx, y: cy - 2, "text-anchor": "middle", style: `font-size:22px;font-weight:700;fill:${css("--text")}` }, root);
      t1.textContent = fmtShort(total);
      const t2 = svg("text", { x: cx, y: cy + 17, "text-anchor": "middle", style: "font-size:11px" }, root);
      t2.textContent = o.centerLabel || "total";
      const lg = document.createElement("div");
      lg.className = "donut-legend";
      lg.innerHTML = o.items.map((it) => `<div class="row"><span><i style="display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:8px;background:${color(it.color)}"></i>${esc(it.label)}</span><b class="num">${fmtInt(it.value)}</b></div>`).join("");
      wrap.appendChild(lg);
    });
  }

  /* ---------------- horizontal bars ---------------- */
  function hbar(el, o) {
    remember(el, () => {
      const rowH = 30, H = Math.max(rowH, o.items.length * rowH) + 4;
      const { w, root, tip } = setup(el, H);
      const labelW = Math.min(130, w * 0.35), valW = 52;
      const max = Math.max(1, ...o.items.map((i) => i.value));
      o.items.forEach((it, k) => {
        const y = k * rowH + 4;
        const t = svg("text", { x: 0, y: y + 15, class: "axis-label", style: `fill:${css("--text")}` }, root);
        t.textContent = it.label;
        svg("rect", { x: labelW, y: y + 4, width: w - labelW - valW, height: 14, rx: 7, fill: css("--line") }, root);
        const bw = Math.max(4, ((w - labelW - valW) * it.value) / max);
        const bar = svg("rect", { x: labelW, y: y + 4, width: bw, height: 14, rx: 7, fill: color(it.color || "--accent"), style: "cursor:default" }, root);
        const v = svg("text", { x: w, y: y + 15, "text-anchor": "end", style: `font-weight:700;fill:${css("--text")}` }, root);
        v.textContent = (o.format || fmtInt)(it.value);
        if (it.tip) {
          bar.addEventListener("mousemove", (e) => { const b = el.getBoundingClientRect(); showTip(tip, e.clientX - b.left, e.clientY - b.top, it.tip); });
          bar.addEventListener("mouseleave", () => tip.classList.add("hidden"));
        }
      });
    });
  }

  /* ---------------- vertical columns (histogram) ---------------- */
  function columns(el, o) {
    remember(el, () => {
      const H = o.height || 220, pad = { l: 44, r: 8, t: 10, b: 40 };
      const { w, root, tip } = setup(el, H);
      const vals = o.values.map((v) => (o.log ? Math.log10(v + 1) : v));
      const max = o.log ? Math.max(1, Math.ceil(Math.max(...vals))) : niceMax(Math.max(1, ...vals));
      const n = vals.length, slot = (w - pad.l - pad.r) / n, bw = Math.max(6, slot * 0.62);
      const Y = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b);
      for (let k = 0; k <= (o.log ? max : 4); k++) {
        const v = o.log ? k : (max * k) / 4, y = Y(v);
        svg("line", { x1: pad.l, x2: w - pad.r, y1: y, y2: y, class: "grid-line" }, root);
        const t = svg("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", class: "axis-label" }, root);
        t.textContent = o.log ? fmtShort(Math.pow(10, k)) : fmtShort(v);
      }
      vals.forEach((v, i) => {
        const x = pad.l + i * slot + (slot - bw) / 2;
        const c = color(typeof o.color === "function" ? o.color(i) : o.color || "--accent");
        const rect = svg("rect", { x, y: Y(v), width: bw, height: Math.max(o.values[i] ? 2 : 0, H - pad.b - Y(v)), rx: 5, fill: c }, root);
        const t = svg("text", { x: x + bw / 2, y: H - pad.b + 14, "text-anchor": "middle", class: "axis-label" }, root);
        t.textContent = o.short ? o.short[i] : o.labels[i];
        rect.addEventListener("mousemove", (e) => { const b = el.getBoundingClientRect(); showTip(tip, e.clientX - b.left, e.clientY - b.top, `${esc(o.labels[i])}: <b>${fmtInt(o.values[i])}</b>`); });
        rect.addEventListener("mouseleave", () => tip.classList.add("hidden"));
      });
      if (o.xTitle) {
        const t = svg("text", { x: (w + pad.l) / 2, y: H - 4, "text-anchor": "middle", class: "axis-label" }, root);
        t.textContent = o.xTitle;
      }
    });
  }

  /* ---------------- grouped bars (model comparison) ---------------- */
  function grouped(el, o) {
    remember(el, () => {
      const H = o.height || 250, pad = { l: 44, r: 8, t: 10, b: 30 };
      const { w, root, tip } = setup(el, H);
      const lo = o.yMin ?? 0, hi = o.yMax ?? 1;
      const Y = (v) => H - pad.b - ((Math.max(lo, v) - lo) / (hi - lo)) * (H - pad.t - pad.b);
      for (let k = 0; k <= 4; k++) {
        const v = lo + ((hi - lo) * k) / 4, y = Y(v);
        svg("line", { x1: pad.l, x2: w - pad.r, y1: y, y2: y, class: "grid-line" }, root);
        const t = svg("text", { x: pad.l - 8, y: y + 4, "text-anchor": "end", class: "axis-label" }, root);
        t.textContent = (o.format || ((x) => x.toFixed(2)))(v);
      }
      const G = o.groups.length, S = o.series.length;
      const slot = (w - pad.l - pad.r) / G, bw = Math.max(5, Math.min(26, (slot * 0.8) / S));
      o.groups.forEach((g, gi) => {
        const x0 = pad.l + gi * slot + (slot - bw * S - (S - 1) * 3) / 2;
        o.series.forEach((s, si) => {
          const v = s.values[gi];
          if (v == null) return;
          const x = x0 + si * (bw + 3);
          const rect = svg("rect", { x, y: Y(v), width: bw, height: Math.max(2, H - pad.b - Y(v)), rx: 4, fill: color(s.color) }, root);
          rect.addEventListener("mousemove", (e) => { const b = el.getBoundingClientRect(); showTip(tip, e.clientX - b.left, e.clientY - b.top, `${esc(s.name)} · ${esc(g)}: <b>${(o.format || ((x) => x.toFixed(3)))(v)}</b>`); });
          rect.addEventListener("mouseleave", () => tip.classList.add("hidden"));
        });
        const t = svg("text", { x: pad.l + gi * slot + slot / 2, y: H - 9, "text-anchor": "middle", style: `font-weight:600;fill:${css("--text")}` }, root);
        t.textContent = g;
      });
    });
  }

  /* ---------------- gauge (0..1) ---------------- */
  function gauge(el, o) {
    remember(el, () => {
      el.innerHTML = "";
      el.classList.add("chart");
      const W = o.size || 200, H = W * 0.62, cx = W / 2, cy = W / 2 - 6, r = W / 2 - 18, sw = 16;
      const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H }, el);
      const arc = (a0, a1) => {
        const p = (a) => [cx + r * Math.cos(Math.PI * (1 - a)), cy - r * Math.sin(Math.PI * (1 - a))];
        const [x0, y0] = p(a0), [x1, y1] = p(a1);
        return `M${x0},${y0} A${r},${r} 0 ${a1 - a0 > 0.5 ? 1 : 0} 1 ${x1},${y1}`;
      };
      svg("path", { d: arc(0, 1), stroke: css("--line"), "stroke-width": sw, fill: "none", "stroke-linecap": "round" }, root);
      (o.marks || []).forEach((m) => {
        const a = Math.PI * (1 - Math.min(1, Math.max(0, m.at)));
        svg("line", { x1: cx + (r - sw) * Math.cos(a), y1: cy - (r - sw) * Math.sin(a), x2: cx + (r + sw) * Math.cos(a), y2: cy - (r + sw) * Math.sin(a), stroke: color(m.color), "stroke-width": 2.5 }, root);
      });
      const v = Math.min(1, Math.max(0, o.value));
      if (v > 0.002) svg("path", { d: arc(0, Math.max(v, 0.01)), stroke: color(o.color || "--accent"), "stroke-width": sw, fill: "none", "stroke-linecap": "round" }, root);
      const t = svg("text", { x: cx, y: cy - 4, "text-anchor": "middle", style: `font-size:26px;font-weight:800;fill:${css("--text")}` }, root);
      t.textContent = o.label ?? v.toFixed(3);
      const s = svg("text", { x: cx, y: cy + 16, "text-anchor": "middle", style: "font-size:11px" }, root);
      s.textContent = o.sub || "fraud score";
    });
  }

  function fmtInt(v) { return v == null ? "–" : Math.round(v).toLocaleString(); }
  function fmtShort(v) {
    if (v == null) return "–";
    const a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + "k";
    return Number.isInteger(v) ? String(v) : v.toFixed(v < 1 ? 2 : 1);
  }

  function rerenderAll() { registry.forEach((el) => (document.body.contains(el) ? el._render() : registry.delete(el))); }

  window.Charts = { line, donut, hbar, columns, grouped, gauge, fmtInt, fmtShort, rerenderAll, css };
})();
