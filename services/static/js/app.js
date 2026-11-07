/* Securelytics dashboard app (vanilla JS single-page app). */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const C = window.Charts;

  /* ------------------------------------------------------------------ icons -- */
  const ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
    zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><line x1="7" y1="6.5" x2="7.01" y2="6.5"/><line x1="7" y1="17.5" x2="7.01" y2="17.5"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
    x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
    shield: '<path d="M12 2l8 3v6c0 5.3-3.4 9.4-8 11-4.6-1.6-8-5.7-8-11V5z"/>',
    activity: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    dollar: '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    check: '<polyline points="20 6 9 17 4 12"/>',
    clock: '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="3"/><line x1="2" y1="10" x2="22" y2="10"/>',
    layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  };
  const icon = (n) => `<span class="ico">${svgIcon(n)}</span>`;
  const svgIcon = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;
  const paintIcons = (root = document) => $$("[data-icon]", root).forEach((el) => { el.innerHTML = svgIcon(el.dataset.icon); el.removeAttribute("data-icon"); });

  /* ------------------------------------------------------------- formatting -- */
  const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])));
  const fInt = (v) => (v == null ? "–" : Math.round(v).toLocaleString());
  const fMoney = (v, d = 0) => (v == null ? "–" : "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const fPct = (v, d = 1) => (v == null ? "–" : (v * 100).toFixed(d) + "%");
  const fMs = (v) => (v == null ? "–" : v < 10 ? v.toFixed(1) + " ms" : Math.round(v) + " ms");
  const fScore = (v) => (v == null ? "–" : v < 0.001 ? v.toExponential(1) : v.toFixed(3));
  const fTime = (s) => (s ? new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "–");
  const fHM = (s) => (s ? new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "–");
  const fDay = (s) => (s ? new Date(s).toLocaleDateString([], { month: "short", day: "numeric" }) : "");
  const fDateTime = (s) => (s ? new Date(s).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "–");
  const fEvent = (s) => (s ? new Date(s).toLocaleString([], { timeZone: "UTC", year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "–");
  const ago = (s) => {
    if (!s) return "never";
    const d = (Date.now() - new Date(s).getTime()) / 1000;
    if (d < 60) return Math.max(0, Math.round(d)) + "s ago";
    if (d < 3600) return Math.round(d / 60) + " min ago";
    if (d < 86400) return Math.round(d / 3600) + " h ago";
    return Math.round(d / 86400) + " d ago";
  };
  const MODEL_LABELS = { hist_gb: "HistGradientBoosting", xgboost: "XGBoost", lightgbm: "LightGBM", catboost: "CatBoost" };
  const mLabel = (n) => MODEL_LABELS[n] || n || "–";
  const decChip = (d) => `<span class="chip ${String(d || "").toLowerCase()}">${esc(d || "–")}</span>`;
  const truthChip = (v) => (v === 1 ? '<span class="chip block plain">fraud</span>' : v === 0 ? '<span class="chip neutral plain">legit</span>' : '<span class="faint">?</span>');
  const reviewChip = (v) => (v === 1 ? '<span class="chip block plain">confirmed fraud</span>' : v === 0 ? '<span class="chip approve plain">marked legit</span>' : '<span class="chip neutral plain">pending</span>');
  const scoreBar = (s, w = 48) => `<div style="display:flex;align-items:center;gap:8px"><div class="bar" style="width:${w}px"><span style="width:${Math.max(2, Math.min(100, s * 100))}%;background:var(${s >= 0.5 ? "--coral" : s >= 0.05 ? "--amber" : "--mint"})"></span></div><span class="num small">${fScore(s)}</span></div>`;
  const appChip = (id) => (String(id || "").startsWith("TXN-") ? ' <span class="chip info plain" title="Made in the payment app">app</span>' : "");
  const reasonText = (rs) => (Array.isArray(rs) ? rs.map((r) => r.text).join(" · ") : "");
  const CATEGORIES = ["entertainment", "food_dining", "gas_transport", "grocery_net", "grocery_pos", "health_fitness", "home", "kids_pets", "misc_net", "misc_pos", "personal_care", "shopping_net", "shopping_pos", "travel"];
  const catLabel = (c) => (c || "").replace("_", " · ");

  /* ------------------------------------------------------------------ state -- */
  const S = {
    page: "overview",
    scope: localStorage.getItem("sl-scope") || "live",
    refresh: Number(localStorage.getItem("sl-refresh") || 10),
    admin: JSON.parse(localStorage.getItem("sl-admin") || "null"),
    status: null,
    catalog: null,
    timer: null,
    busy: false,
  };

  /* -------------------------------------------------------------------- api -- */
  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (S.admin) headers["X-Admin-Token"] = S.admin.token;
    try {
      const res = await fetch(path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return { ok: false, status: res.status, error: data.error || "error", message: data.message || res.statusText };
      return { ok: true, data };
    } catch (e) {
      return { ok: false, status: 0, error: "network", message: "Cannot reach the dashboard server. Is the 'web' container running?" };
    }
  }

  function toast(msg, kind = "") {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.innerHTML = `${icon(kind === "bad" ? "alert" : "check")}<span>${esc(msg)}</span>`;
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), 3600);
  }

  function errorBox(r) {
    return `<div class="empty">${icon("alert")}<div class="strong">${esc(r.message || "Something went wrong")}</div>
      ${r.error === "database_unavailable" ? '<pre class="cmd" style="text-align:left;margin-top:12px">docker compose ps\ndocker compose up -d postgres\ndocker compose logs postgres --tail 50</pre>' : ""}</div>`;
  }

  /* ---------------------------------------------------------------- status -- */
  async function loadStatus() {
    const r = await api("/api/status");
    const banner = $("#banner");
    if (!r.ok) {
      S.status = null;
      banner.className = "banner bad";
      banner.innerHTML = `${icon("alert")}<div><b>Dashboard server unreachable.</b> ${esc(r.message)}</div>`;
      $("#status-dots").innerHTML = '<span class="dot bad"></span>';
      return;
    }
    const st = (S.status = r.data);
    const procMsg = st.processor.ok ? `running · ${fInt(st.processor.processed)} processed since start` : st.processor.age_s ? `last seen ${Math.round(st.processor.age_s)}s ago` : "not running";
    $("#status-dots").innerHTML = [
      ["Database (Postgres)", st.db.ok ? "ok" : "bad", st.db.ok ? "connected" : st.db.error],
      ["Feature store (Redis)", st.redis.ok ? "ok" : "bad", st.redis.ok ? "connected" : st.redis.error],
      ["Stream processor", st.processor.ok ? "ok" : "warn", procMsg],
    ].map(([n, c, m]) => `<span class="dot ${c}" title="${esc(n)}: ${esc(m || "")}"></span>`).join("");

    let html = "", cls = "";
    if (!st.db.ok) {
      cls = "bad";
      html = `${icon("database")}<div><b>Database offline.</b> The dashboard can't reach Postgres, so no data can be shown.
        Run <code>docker compose ps</code> to check the <code>postgres</code> container, start it with <code>docker compose up -d postgres</code>,
        and check <code>docker compose logs postgres</code> if it keeps stopping.</div>`;
    } else if (!st.redis.ok) {
      cls = "bad";
      html = `${icon("alert")}<div><b>Redis offline.</b> Live scoring and model switching need Redis. Run <code>docker compose up -d redis</code>.</div>`;
    } else if (!st.processor.ok) {
      cls = "warn";
      html = `${icon("activity")}<div><b>Stream processor not running</b> (${esc(procMsg)}). Data below may be stale.
        Start the pipeline with <code>docker compose up -d processor producer</code>.</div>`;
    } else if (!st.db.transactions) {
      cls = "warn";
      html = `${icon("inbox")}<div><b>No transactions yet.</b> The producer replays <code>data/raw/fraudTest.csv</code>; check <code>docker compose logs producer</code>.</div>`;
    }
    banner.className = html ? `banner ${cls}` : "banner hidden";
    banner.innerHTML = html;
    $("#side-model-name").textContent = mLabel(st.models.active);
    const pending = st.db.ok ? st.db.alerts_pending_review : null;
    $("#nav-alerts").textContent = pending ? (pending > 999 ? "999+" : pending) : "";
  }

  async function loadCatalog(force) {
    if (S.catalog && !force) return S.catalog;
    const r = await api("/api/models?window=100");
    if (r.ok) S.catalog = Object.fromEntries(r.data.catalog.map((m) => [m.name, m]));
    return S.catalog || {};
  }

  /* ------------------------------------------------------------- pages ------ */
  const PAGES = {};

  /* ---------- Overview ---------- */
  PAGES.overview = {
    title: "Overview",
    sub: () => (S.scope === "live" ? `Metrics for the live model: ${mLabel(S.status?.models?.active)}` : "Metrics across all models"),
    scope: true,
    auto: true,
    init(v) {
      v.innerHTML = `
        <section class="grid kpis" id="kpis">${'<div class="card kpi"><div class="skeleton" style="height:60px"></div></div>'.repeat(6)}</section>
        <section class="grid g-2-1">
          <div class="card"><div class="card-head"><div><h2>Traffic &amp; alerts</h2><div class="muted">Transactions and alerts per minute</div></div>
            <div class="seg neu-inset" id="ov-min"><button data-m="30">30m</button><button data-m="60" class="on">1h</button><button data-m="360">6h</button></div></div>
            <div id="ch-traffic"></div><div class="legend" style="margin-top:8px"><span><i style="background:var(--accent)"></i>Transactions</span><span><i style="background:var(--amber)"></i>Alerts</span><span><i style="background:var(--coral)"></i>Blocked</span></div></div>
          <div class="card"><div class="card-head"><div><h2>Decisions</h2><div class="muted">Share of all scored transactions</div></div></div><div id="ch-decisions"></div></div>
        </section>
        <section class="grid g-1-1">
          <div class="card"><div class="card-head"><div><h2>Alerts by category</h2><div class="muted">Where flagged transactions happen</div></div></div><div id="ch-cats"></div></div>
          <div class="card"><div class="card-head"><div><h2>Score distribution</h2><div class="muted">Fraud scores of all transactions (log scale)</div></div></div><div id="ch-scores"></div></div>
        </section>
        <section class="card"><div class="card-head"><div><h2>Latest alerts</h2><div class="muted">Click an alert for details and to review it</div></div>
          <a class="btn small" href="#/alerts">View all alerts</a></div><div id="ov-alerts" class="alert-list"></div></section>`;
      S.ovMinutes = S.ovMinutes || 60;
      $$("#ov-min button", v).forEach((b) => {
        b.classList.toggle("on", Number(b.dataset.m) === S.ovMinutes);
        b.onclick = () => { S.ovMinutes = Number(b.dataset.m); $$("#ov-min button").forEach((x) => x.classList.toggle("on", x === b)); this.load(); };
      });
    },
    async load() {
      const r = await api(`/api/overview?scope=${S.scope}&minutes=${S.ovMinutes || 60}`);
      const rest = $$("#view > section").slice(1);
      if (!r.ok) { $("#kpis").innerHTML = `<div class="card" style="grid-column:1/-1">${errorBox(r)}</div>`; rest.forEach((x) => x.classList.add("hidden")); return; }
      rest.forEach((x) => x.classList.remove("hidden"));
      const d = r.data, k = d.kpi;
      $("#page-sub").textContent = this.sub();
      const kpi = (label, value, sub, ic, cls) => `<div class="card kpi"><div class="kpi-top"><span class="kpi-label">${label}</span><span class="kpi-icon ${cls}">${icon(ic)}</span></div><div class="kpi-value">${value}</div><div class="kpi-sub">${sub}</div></div>`;
      $("#kpis").innerHTML = [
        kpi("Transactions scored", fInt(k.processed), `${fInt((k.tps || 0) * 60)}/min now · ${fMoney(k.volume_amt)} volume`, "activity", "ic-lav"),
        kpi("Alerts raised", fInt(k.alerts), `${fInt(k.review)} review · ${fInt(k.blocked)} blocked · ${fPct(k.alert_rate, 2)} of txns`, "bell", "ic-amber"),
        kpi("Fraud $ caught", fMoney(k.fraud_flagged_amt), `of ${fMoney(k.fraud_total_amt)} fraud · ${fMoney(k.fraud_blocked_amt)} blocked`, "dollar", "ic-mint"),
        kpi("Precision", fPct(k.precision), "alerts that were real fraud", "target", "ic-sky"),
        kpi("Recall", fPct(k.recall), `${fInt(k.fraud_flagged)} of ${fInt(k.fraud_total)} frauds caught`, "shield", "ic-coral"),
        kpi("Scoring latency", fMs(k.p50_ms), `p95 ${fMs(k.p95_ms)} · end-to-end ${fMs(k.e2e_p50_ms)}`, "clock", "ic-lav"),
      ].join("");
      const lab = d.series.map((p) => p.minute);
      C.line($("#ch-traffic"), {
        labels: lab, height: 250,
        xFormat: (s, long) => new Date(s).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + (long ? "" : ""),
        series: [
          { name: "Transactions", values: d.series.map((p) => p.txns), color: "--accent" },
          { name: "Alerts", values: d.series.map((p) => p.alerts), color: "--amber", bars: true },
          { name: "Blocked", values: d.series.map((p) => p.blocked), color: "--coral", bars: true },
        ],
      });
      const dec = Object.fromEntries(d.decisions.map((x) => [x.decision, x.n]));
      C.donut($("#ch-decisions"), {
        centerLabel: "transactions",
        items: [{ label: "Approved", value: dec.APPROVE || 0, color: "--mint" }, { label: "Review", value: dec.REVIEW || 0, color: "--amber" }, { label: "Blocked", value: dec.BLOCK || 0, color: "--coral" }],
      });
      const cats = d.categories;
      if (cats.length) {
        C.hbar($("#ch-cats"), {
          items: cats.map((c) => ({ label: catLabel(c.category), value: c.alerts, color: "--lav",
            tip: `<b>${esc(c.category)}</b><br>${fInt(c.alerts)} alerts · ${fInt(c.confirmed_fraud)} real fraud<br>${fMoney(c.amount)}` })),
        });
      } else $("#ch-cats").innerHTML = `<div class="empty">${icon("inbox")}<div>No alerts yet</div></div>`;
      C.columns($("#ch-scores"), {
        labels: d.score_hist.map((b) => b.bucket), values: d.score_hist.map((b) => b.n), log: true, height: 230,
        short: ["0", ".001", ".01", ".05", ".1", ".2", ".3", ".5", ".7", ".9"],
        color: (i) => (i >= 7 ? "--coral" : i >= 3 ? "--amber" : "--mint"), xTitle: "fraud score (bucket start)",
      });
      $("#ov-alerts").innerHTML = d.recent_alerts.length
        ? d.recent_alerts.map((a) => `<div class="alert-item" data-id="${esc(a.trans_id)}" tabindex="0" role="button">
            ${decChip(a.decision)}
            <div style="min-width:0"><div class="cell-main">${esc(a.merchant)}${appChip(a.trans_id)} <span class="muted small">· ${esc(a.category)} · ****${esc(a.card_last4)}</span></div>
            <div class="reason-line">${esc(reasonText(a.reasons))}</div></div>
            <div class="right"><div class="alert-amt">${fMoney(a.amt, 2)}</div><div class="muted small">${ago(a.created_at)} · ${esc(mLabel(a.model_name))}</div></div></div>`).join("")
        : `<div class="empty">${icon("inbox")}<div>No alerts yet</div></div>`;
      $$("#ov-alerts .alert-item").forEach((el) => { el.onclick = () => openAlert(el.dataset.id); el.onkeydown = (e) => e.key === "Enter" && openAlert(el.dataset.id); });
    },
  };

  /* ---------- shared table page builder (alerts / transactions) ---------- */
  function tablePage(kind) {
    const isAlerts = kind === "alerts";
    return {
      title: isAlerts ? "Alerts" : "Transactions",
      sub: () => (isAlerts ? "Every transaction flagged for REVIEW or BLOCK, newest first" : "Every scored transaction, newest first"),
      auto: true,
      f: { q: "", decision: "", category: "", truth: "", review: "", model: "", offset: 0, limit: 25 },
      async init(v) {
        const f = this.f;
        v.innerHTML = `<section class="card">
          <div class="toolbar">
            <div class="toolbar-row"><div class="search">${icon("search")}<input class="input" id="t-q" placeholder="Search merchant, card last 4 or transaction id" value="${esc(f.q)}"></div><button class="btn small" id="t-reset">Reset filters</button></div>
            <div class="seg neu-inset" id="t-dec">${(isAlerts ? ["", "REVIEW", "BLOCK"] : ["", "APPROVE", "REVIEW", "BLOCK"]).map((d) => `<button data-v="${d}" class="${f.decision === d ? "on" : ""}">${d ? d[0] + d.slice(1).toLowerCase() : "All"}</button>`).join("")}</div>
            <div class="select-box"><select class="input select" id="t-cat"><option value="">All categories</option>${CATEGORIES.map((c) => `<option ${f.category === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
            <div class="select-box"><select class="input select" id="t-truth"><option value="">Any truth</option><option value="fraud">Actually fraud</option><option value="legit">Actually legit</option></select></div>
            ${isAlerts ? '<div class="select-box"><select class="input select" id="t-review"><option value="">Any review status</option><option value="pending">Pending review</option><option value="done">Reviewed</option></select></div>' : ""}
            <div class="select-box"><select class="input select" id="t-model"><option value="">All models</option>${Object.keys(MODEL_LABELS).map((m) => `<option value="${m}">${MODEL_LABELS[m]}</option>`).join("")}</select></div>
          </div>
          <div class="table-wrap" id="t-table"><div class="skeleton" style="height:240px"></div></div>
          <div class="pager"><span class="muted small" id="t-count"></span>
            <div style="display:flex;gap:10px;align-items:center"><button class="btn small" id="t-prev">Previous</button><span class="small muted" id="t-page"></span><button class="btn small" id="t-next">Next</button></div></div>
        </section>`;
        ["truth", "review", "model"].forEach((k) => { const el = $(`#t-${k}`); if (el) el.value = f[k]; });
        let deb;
        $("#t-q").oninput = (e) => { clearTimeout(deb); deb = setTimeout(() => { f.q = e.target.value.trim(); f.offset = 0; this.load(); }, 300); };
        $$("#t-dec button").forEach((b) => (b.onclick = () => { f.decision = b.dataset.v; f.offset = 0; $$("#t-dec button").forEach((x) => x.classList.toggle("on", x === b)); this.load(); }));
        [["cat", "category"], ["truth", "truth"], ["review", "review"], ["model", "model"]].forEach(([id, key]) => { const el = $(`#t-${id}`); if (el) el.onchange = () => { f[key] = el.value; f.offset = 0; this.load(); }; });
        $("#t-reset").onclick = () => { Object.assign(f, { q: "", decision: "", category: "", truth: "", review: "", model: "", offset: 0 }); this.init(v); this.load(); };
        $("#t-prev").onclick = () => { f.offset = Math.max(0, f.offset - f.limit); this.load(); };
        $("#t-next").onclick = () => { f.offset += f.limit; this.load(); };
      },
      async load() {
        const f = this.f;
        const qs = new URLSearchParams(Object.entries(f).filter(([, val]) => val !== "" && val != null)).toString();
        const r = await api(`/api/${kind}?${qs}`);
        if (!r.ok) { $("#t-table").innerHTML = errorBox(r); return; }
        const { items, total } = r.data;
        if (!items.length) {
          $("#t-table").innerHTML = `<div class="empty">${icon("inbox")}<div class="strong">Nothing matches these filters</div><div class="small">Try clearing a filter or the search box.</div></div>`;
        } else if (isAlerts) {
          $("#t-table").innerHTML = `<table class="tbl"><thead><tr><th>Time</th><th>Decision</th><th>Score</th><th>Card</th><th>Merchant · reasons</th><th class="right">Amount</th><th>Model</th><th>Truth</th><th>Review</th></tr></thead><tbody>
            ${items.map((a) => `<tr class="clickable" data-id="${esc(a.trans_id)}" tabindex="0"><td class="nowrap"><div class="cell-main num">${fHM(a.created_at)}</div><div class="cell-sub">${fDay(a.created_at)}</div></td>
              <td>${decChip(a.decision)}</td><td>${scoreBar(a.score)}</td><td class="mono">****${esc(a.card_last4)}</td>
              <td><div class="cell-main">${esc(a.merchant)}${appChip(a.trans_id)} <span class="muted small">· ${esc(a.category)}</span></div><div class="reason-line">${esc(reasonText(a.reasons))}</div></td>
              <td class="right num strong">${fMoney(a.amt, 2)}</td><td class="small">${esc(mLabel(a.model_name))}</td><td>${truthChip(a.is_fraud)}</td><td>${reviewChip(a.analyst_label)}</td></tr>`).join("")}</tbody></table>`;
        } else {
          $("#t-table").innerHTML = `<table class="tbl"><thead><tr><th>Processed</th><th>Decision</th><th>Score</th><th>Card</th><th>Merchant</th><th>Category</th><th class="right">Amount</th><th>Model</th><th>Truth</th><th class="right">Latency</th></tr></thead><tbody>
            ${items.map((t) => `<tr class="clickable" data-id="${esc(t.trans_id)}" data-dec="${t.decision}" tabindex="0"><td class="nowrap"><div class="cell-main num">${fHM(t.processed_at)}</div><div class="cell-sub">${fDay(t.processed_at)}</div></td><td>${decChip(t.decision)}</td><td>${scoreBar(t.score)}</td>
              <td class="mono">****${esc(t.card_last4)}</td><td class="cell-main">${esc(t.merchant)}${appChip(t.trans_id)}</td><td class="small muted">${esc(t.category)}</td><td class="right num strong">${fMoney(t.amt, 2)}</td>
              <td class="small">${esc(mLabel(t.model_name))}</td><td>${truthChip(t.is_fraud)}</td><td class="right num small">${fMs(t.scoring_ms)}</td></tr>`).join("")}</tbody></table>`;
        }
        $$("#t-table tr.clickable").forEach((tr) => {
          const open = () => (tr.dataset.dec === "APPROVE" ? openTxn(items.find((x) => x.trans_id === tr.dataset.id)) : openAlert(tr.dataset.id));
          tr.onclick = open;
          tr.onkeydown = (e) => e.key === "Enter" && open();
        });
        const page = Math.floor(f.offset / f.limit) + 1, pages = Math.max(1, Math.ceil(total / f.limit));
        $("#t-count").textContent = `${fInt(total)} ${kind}`;
        $("#t-page").textContent = `Page ${page} of ${fInt(pages)}`;
        $("#t-prev").disabled = f.offset === 0;
        $("#t-next").disabled = f.offset + f.limit >= total;
      },
    };
  }
  PAGES.alerts = tablePage("alerts");
  PAGES.transactions = tablePage("transactions");

  /* ---------- Models ---------- */
  PAGES.models = {
    title: "Models",
    sub: () => "Compare the four models and choose which one decides on live traffic",
    auto: true,
    window: 20000,
    init(v) {
      v.innerHTML = `
        <section class="card" id="m-live"><div class="skeleton" style="height:90px"></div></section>
        <section class="grid g-4" id="m-cards"></section>
        <section class="grid g-1-1">
          <div class="card"><div class="card-head"><div><h2>Offline comparison</h2><div class="muted">Unseen test period · 555,719 transactions · at each model's BLOCK threshold</div></div></div>
            <div id="m-chart"></div><div class="legend" id="m-legend" style="margin-top:8px"></div></div>
          <div class="card"><div class="card-head"><div><h2>Live comparison (shadow scoring)</h2><div class="muted">All models score the same live transactions; only the live model decides</div></div>
            <div class="select-box"><select class="input select" id="m-window" style="width:auto"><option value="5000">Last 5k</option><option value="20000" selected>Last 20k</option><option value="100000">Last 100k</option></select></div></div>
            <div class="table-wrap" id="m-live-table"></div></div>
        </section>
        <section class="card"><div class="card-head"><div><h2>Full offline metrics</h2><div class="muted">Accuracy is ~99.6% even for a model that never flags fraud, so compare PR-AUC, recall and false blocks</div></div></div><div class="table-wrap" id="m-offline"></div></section>
        <section class="grid g-2-1">
          <div class="card"><div class="card-head"><div><h2>Actual decisions by model</h2><div class="muted">What each model decided while it was live</div></div></div><div class="table-wrap" id="m-actual"></div></div>
          <div class="card"><div class="card-head"><div><h2>Switch history</h2><div class="muted">Audit log of admin model switches</div></div></div><div class="table-wrap" id="m-switches"></div></div>
        </section>`;
      $("#m-window").value = String(this.window);
      $("#m-window").onchange = (e) => { this.window = Number(e.target.value); this.load(); };
    },
    async load() {
      const r = await api(`/api/models?window=${this.window}`);
      if (!r.ok) { $("#m-live").innerHTML = errorBox(r); return; }
      const d = r.data;
      S.catalog = Object.fromEntries(d.catalog.map((m) => [m.name, m]));
      const live = S.catalog[d.active];
      const lastSwitch = d.switches[0];
      const trained = d.catalog.filter((m) => m.trained && m.loaded);
      $("#m-live").innerHTML = `<div class="card-head" style="margin:0;flex-wrap:wrap">
        <div style="display:flex;gap:16px;align-items:center"><span class="kpi-icon ic-lav" style="width:46px;height:46px">${icon("cpu")}</span>
          <div><div class="muted small">Live model (decides every transaction)</div><div style="font-size:20px;font-weight:700">${esc(mLabel(d.active))}</div>
          <div class="muted small">${live ? `REVIEW ≥ ${fScore(live.thresholds.review)} · BLOCK ≥ ${fScore(live.thresholds.block)} · ` : ""}${lastSwitch ? `switched ${ago(lastSwitch.switched_at)} by ${esc(lastSwitch.switched_by)}` : "default model (best on validation)"}</div></div></div>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          ${S.admin ? `<div class="select-box"><select class="input select" id="m-pick">${trained.map((m) => `<option value="${m.name}" ${m.name === d.active ? "selected" : ""}>${esc(mLabel(m.name))}</option>`).join("")}</select></div>
            <input class="input" id="m-note" placeholder="Reason (optional)" style="width:200px"><button class="btn primary" id="m-activate">Activate</button>`
            : `<span class="muted small">${S.status?.admin_enabled === false ? "Admin is disabled (set ADMIN_PASSWORD in .env)" : "Log in as admin to switch models"}</span><button class="btn" id="m-login">${icon("lock")}Admin login</button>`}
        </div></div>`;
      if ($("#m-activate")) $("#m-activate").onclick = () => switchModel($("#m-pick").value, $("#m-note").value);
      if ($("#m-login")) $("#m-login").onclick = openLogin;

      const metric = (name, v, col) => `<div class="metric-row"><span class="muted">${name}</span><div class="bar"><span style="width:${v == null ? 0 : Math.max(2, v * 100)}%;background:var(${col})"></span></div><span class="v">${v == null ? "–" : v.toFixed(3)}</span></div>`;
      $("#m-cards").innerHTML = d.catalog.map((m) => {
        const t = m.test || {};
        const isLive = m.name === d.active;
        return `<div class="card model-card ${isLive ? "is-live" : ""}">
          <div class="model-head"><div><h2>${esc(mLabel(m.name))}</h2><div class="muted small">${m.trained ? `${fInt(m.n_trees)} trees · trained ${fDateTime(m.trained_at)}` : "Run the trainer to create it"}</div></div>
          ${isLive ? '<span class="chip lav badge-live">LIVE</span>' : m.trained ? '<span class="chip neutral plain badge-live">standby</span>' : '<span class="chip review plain badge-live">not trained</span>'}</div>
          ${m.trained ? `${metric("PR-AUC", t.pr_auc, "--accent")}${metric("ROC-AUC", t.roc_auc, "--sky")}${metric("Precision", t.precision_block, "--mint")}${metric("Recall", t.recall_block, "--amber")}${metric("F1", t.f1_block, "--lav")}
          <div class="kv"><div><span>False blocks</span><span>${fInt(t.fp_block)}</span></div><div><span>Missed fraud</span><span>${fInt(t.fn_block)}</span></div>
          <div><span>Latency</span><span>${fMs(t.latency_p50_ms)}</span></div><div><span>Accuracy</span><span>${fPct(t.accuracy_block, 2)}</span></div></div>
          ${S.admin ? `<button class="btn ${isLive ? "" : "primary"}" data-activate="${m.name}" ${isLive || !m.loaded ? "disabled" : ""}>${isLive ? "Currently live" : m.loaded ? "Make live" : "Library not installed"}</button>` : ""}`
          : '<div class="empty" style="padding:18px">' + icon("layers") + '<div class="small">No metrics yet</div></div>'}
        </div>`;
      }).join("");
      $$("[data-activate]").forEach((b) => (b.onclick = () => switchModel(b.dataset.activate, "")));

      const tm = d.catalog.filter((m) => m.trained);
      const palette = ["--accent", "--sky", "--mint", "--coral"];
      if (tm.length) {
        C.grouped($("#m-chart"), {
          groups: ["PR-AUC", "Precision", "Recall", "F1"], yMin: 0.85, yMax: 1, height: 260,
          series: tm.map((m, i) => ({ name: mLabel(m.name), color: palette[i % 4], values: [m.test.pr_auc, m.test.precision_block, m.test.recall_block, m.test.f1_block] })),
        });
        $("#m-legend").innerHTML = tm.map((m, i) => `<span><i style="background:var(${palette[i % 4]})"></i>${esc(mLabel(m.name))}</span>`).join("");
      }
      $("#m-offline").innerHTML = tm.length ? `<table class="tbl"><thead><tr><th>Model</th><th class="right">PR-AUC</th><th class="right">ROC-AUC</th><th class="right">Accuracy</th><th class="right">Precision</th><th class="right">Recall</th><th class="right">F1</th><th class="right">False blocks</th><th class="right">Missed fraud</th><th class="right">Recall @ review</th><th class="right">Latency</th></tr></thead><tbody>
        ${tm.slice().sort((a, b) => b.test.pr_auc - a.test.pr_auc).map((m) => { const t = m.test; return `<tr class="${m.name === d.active ? "hl" : ""}"><td class="cell-main">${esc(mLabel(m.name))}${m.name === d.default ? ' <span class="chip info plain">default</span>' : ""}</td>
          <td class="right num strong">${t.pr_auc.toFixed(4)}</td><td class="right num">${t.roc_auc.toFixed(4)}</td><td class="right num">${fPct(t.accuracy_block, 3)}</td><td class="right num">${fPct(t.precision_block)}</td>
          <td class="right num">${fPct(t.recall_block)}</td><td class="right num">${t.f1_block.toFixed(3)}</td><td class="right num">${fInt(t.fp_block)}</td><td class="right num">${fInt(t.fn_block)}</td><td class="right num">${fPct(t.recall_review)}</td><td class="right num">${fMs(t.latency_p50_ms)}</td></tr>`; }).join("")}</tbody></table>` : `<div class="empty">No trained models</div>`;

      $("#m-live-table").innerHTML = d.live.length ? `<table class="tbl"><thead><tr><th>Model</th><th class="right">Txns</th><th class="right">Fraud</th><th class="right">PR-AUC</th><th class="right">Precision</th><th class="right">Recall</th><th class="right">False blocks</th><th class="right">$ caught</th></tr></thead><tbody>
        ${d.live.map((m) => `<tr class="${m.model === d.active ? "hl" : ""}"><td class="cell-main">${esc(mLabel(m.model))}</td><td class="right num">${fInt(m.transactions)}</td><td class="right num">${fInt(m.fraud_in_window)}</td>
          <td class="right num strong">${m.pr_auc == null ? "–" : m.pr_auc.toFixed(3)}</td><td class="right num">${fPct(m.precision_block)}</td><td class="right num">${fPct(m.recall_block)}</td>
          <td class="right num">${fInt(m.false_alerts_block)}</td><td class="right num">${fMoney(m.fraud_amt_caught_review)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">${icon("inbox")}<div>No live transactions yet</div></div>`;

      $("#m-actual").innerHTML = d.by_model.length ? `<table class="tbl"><thead><tr><th>Model</th><th class="right">Txns</th><th class="right">Review</th><th class="right">Blocked</th><th class="right">Recall</th><th class="right">False blocks</th><th>Last used</th></tr></thead><tbody>
        ${d.by_model.map((m) => `<tr><td class="cell-main">${esc(mLabel(m.model_name))}</td><td class="right num">${fInt(m.txns)}</td><td class="right num">${fInt(m.review)}</td><td class="right num">${fInt(m.blocked)}</td>
          <td class="right num">${m.fraud_total ? fPct(m.fraud_flagged / m.fraud_total) : "–"}</td><td class="right num">${fInt(m.good_blocked)}</td><td class="small muted nowrap">${ago(m.last_used)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">No decisions yet</div>`;
      $("#m-switches").innerHTML = d.switches.length ? `<table class="tbl"><thead><tr><th>When</th><th>Change</th><th>By</th><th>Reason</th></tr></thead><tbody>
        ${d.switches.map((s) => `<tr><td class="small nowrap">${fDateTime(s.switched_at)}</td><td>${esc(mLabel(s.from_model))} → <b>${esc(mLabel(s.to_model))}</b></td><td>${esc(s.switched_by)}</td><td class="small muted">${esc(s.note || "–")}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">${icon("clock")}<div>No switches yet</div></div>`;
    },
  };

  async function switchModel(name, note) {
    if (!S.admin) return openLogin();
    const r = await api("/api/models/active", { method: "POST", body: JSON.stringify({ name, note }) });
    if (r.ok) {
      toast(`${mLabel(name)} is now live. The processor switches within about a second.`, "ok");
      await loadStatus();
      PAGES.models.load();
    } else {
      if (r.status === 401) setAdmin(null);
      toast(r.message, "bad");
    }
  }

  /* ---------- Score tester ---------- */
  const PROFILE = { cc_num: "2291163933867244", gender: "M", dob: "1968-03-19", city_pop: 333497, lat: 33.9659, long: -80.9355, merch_lat: 33.986391, merch_long: -81.200714 };
  const PRESETS = {
    normal: { label: "Everyday grocery", v: { ...PROFILE, amt: 42.1, category: "grocery_pos", merchant: "Kirlin and Sons", when: "2020-12-31T14:05" } },
    night: { label: "Late-night online splurge", v: { ...PROFILE, amt: 1049.99, category: "shopping_net", merchant: "Fisher-Schowalter", when: "2020-12-31T23:10" } },
    gas: { label: "Morning fuel stop", v: { ...PROFILE, amt: 38.5, category: "gas_transport", merchant: "Kuhn LLC", when: "2020-12-31T08:20" } },
    far: { label: "Big purchase far away", v: { ...PROFILE, amt: 980, category: "misc_net", merchant: "Remote Store", when: "2020-12-31T02:40", merch_lat: 47.6, merch_long: -122.3 } },
  };
  PAGES.score = {
    title: "Score tester",
    sub: () => "Score any transaction with the live model, using the card's real history from the feature store (nothing is saved)",
    auto: false,
    init(v) {
      v.innerHTML = `<section class="grid g-1-1">
        <form class="card" id="sc-form" novalidate>
          <div class="card-head"><div><h2>Transaction</h2><div class="muted">Pick a preset or fill in your own</div></div></div>
          <div class="presets" style="margin-bottom:16px">${Object.entries(PRESETS).map(([k, p]) => `<button type="button" class="btn small" data-preset="${k}">${esc(p.label)}</button>`).join("")}</div>
          <div class="form-grid">
            <label class="field">Amount ($)<input class="input" name="amt" type="number" step="0.01" min="0.01" required></label>
            <label class="field">Category<div class="select-box"><select class="input select" name="category">${CATEGORIES.map((c) => `<option>${c}</option>`).join("")}</select></div></label>
            <label class="field">Merchant<input class="input" name="merchant" required maxlength="80"></label>
            <label class="field">Date &amp; time<input class="input" name="when" type="datetime-local" required></label>
            <label class="field">Card number<input class="input mono" name="cc_num" required pattern="[0-9]{12,19}" inputmode="numeric"></label>
            <label class="field">Cardholder gender<div class="select-box"><select class="input select" name="gender"><option value="M">M</option><option value="F">F</option></select></div></label>
            <label class="field">Date of birth<input class="input" name="dob" type="date" required></label>
            <label class="field">City population<input class="input" name="city_pop" type="number" min="1" required></label>
            <label class="field">Customer latitude<input class="input" name="lat" type="number" step="any" required></label>
            <label class="field">Customer longitude<input class="input" name="long" type="number" step="any" required></label>
            <label class="field">Merchant latitude<input class="input" name="merch_lat" type="number" step="any" required></label>
            <label class="field">Merchant longitude<input class="input" name="merch_long" type="number" step="any" required></label>
          </div>
          <div class="form-error" id="sc-error" style="margin-top:14px"></div>
          <div class="row-end" style="margin-top:16px"><button type="submit" class="btn primary" id="sc-submit">${icon("zap")}Score transaction</button></div>
        </form>
        <div class="card" id="sc-result"><div class="empty">${icon("zap")}<div class="strong">No result yet</div><div class="small">Choose a preset or fill the form, then press “Score transaction”.</div></div></div>
      </section>`;
      const form = $("#sc-form");
      const fill = (p) => Object.entries(p).forEach(([k, val]) => { if (form.elements[k]) form.elements[k].value = val; });
      fill(PRESETS.night.v);
      $$("[data-preset]").forEach((b) => (b.onclick = () => { fill(PRESETS[b.dataset.preset].v); $$("[data-preset]").forEach((x) => x.classList.toggle("pressed", x === b)); form.requestSubmit(); }));
      form.onsubmit = async (e) => {
        e.preventDefault();
        $("#sc-error").textContent = "";
        const bad = $$("input", form).filter((i) => !i.checkValidity());
        if (bad.length) { $("#sc-error").textContent = `Please check: ${bad.map((i) => i.closest("label").childNodes[0].textContent.trim()).join(", ")}`; bad[0].focus(); return; }
        const fd = Object.fromEntries(new FormData(form).entries());
        const body = {
          trans_num: "ui-" + Math.random().toString(36).slice(2, 12), trans_date_trans_time: fd.when.replace("T", " ") + ":00",
          cc_num: fd.cc_num, merchant: fd.merchant, category: fd.category, amt: Number(fd.amt), gender: fd.gender,
          lat: Number(fd.lat), long: Number(fd.long), city_pop: Number(fd.city_pop), dob: fd.dob, merch_lat: Number(fd.merch_lat), merch_long: Number(fd.merch_long),
        };
        const btn = $("#sc-submit"); btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Scoring…';
        const r = await api("/api/score", { method: "POST", body: JSON.stringify(body) });
        btn.disabled = false; btn.innerHTML = `${icon("zap")}Score transaction`;
        if (!r.ok) { $("#sc-error").textContent = r.message; return; }
        renderScore(r.data);
      };
    },
    load() {},
  };

  async function renderScore(res) {
    const cat = await loadCatalog();
    const m = cat[res.model_name] || {};
    const thr = m.thresholds || { review: 0.5, block: 0.9 };
    const col = res.decision === "BLOCK" ? "--coral" : res.decision === "REVIEW" ? "--amber" : "--mint";
    const f = res.features || {};
    $("#sc-result").innerHTML = `
      <div class="card-head"><div><h2>Result</h2><div class="muted">Decided by ${esc(mLabel(res.model_name))} in ${fMs(res.scoring_ms)}</div></div>${decChip(res.decision)}</div>
      <div class="result-hero"><div id="sc-gauge"></div>
        <div><div class="decision-big" style="color:var(${col === "--mint" ? "--mint-ink" : col === "--amber" ? "--amber-ink" : "--coral-ink"})">${esc(res.decision)}</div>
        <div class="muted small">Model said ${esc(res.model_decision)}${res.rules_fired.length ? ` · rules fired: ${res.rules_fired.map(esc).join(", ")}` : ""}</div>
        <div class="muted small" style="margin-top:6px">REVIEW ≥ ${fScore(thr.review)} · BLOCK ≥ ${fScore(thr.block)}</div></div></div>
      <div><div class="section-title">Why</div>${reasonsHtml(res.reasons, res.decision)}</div>
      <div><div class="section-title">What every model thinks</div>${shadowHtml(res.shadow_scores, cat, res.model_name)}</div>
      <div><div class="section-title">Key features (from the card's live history)</div>${featuresHtml(f)}</div>`;
    $("#sc-result").style.display = "flex"; $("#sc-result").style.flexDirection = "column"; $("#sc-result").style.gap = "18px";
    C.gauge($("#sc-gauge"), { value: res.score, color: col, label: fScore(res.score), marks: [{ at: thr.review, color: "--amber" }, { at: thr.block, color: "--coral" }] });
  }

  function reasonsHtml(reasons, decision) {
    if (!reasons || !reasons.length) return `<div class="muted small">${decision === "APPROVE" ? "Nothing unusual: the transaction matches this card's normal behaviour." : "No reason codes recorded."}</div>`;
    const max = Math.max(0.01, ...reasons.map((r) => r.impact || 0));
    return `<ul class="reasons">${reasons.map((r) => r.factor.startsWith("rule:")
      ? `<li class="rule"><span><b>Rule:</b> ${esc(r.text)}</span><span class="small right">expert rule</span></li>`
      : `<li><span>${esc(r.text)}</span><div class="bar" title="impact on score: ${(r.impact || 0).toFixed(3)}"><span style="width:${Math.max(4, ((r.impact || 0) / max) * 100)}%;background:var(--coral)"></span></div></li>`).join("")}</ul>`;
  }

  function shadowHtml(scores, cat, active) {
    if (!scores) return '<div class="muted small">–</div>';
    return `<table class="tbl"><tbody>${Object.entries(scores).map(([name, s]) => {
      const t = cat[name]?.thresholds;
      const would = t ? (s >= t.block ? "BLOCK" : s >= t.review ? "REVIEW" : "APPROVE") : null;
      return `<tr class="${name === active ? "hl" : ""}"><td class="cell-main">${esc(mLabel(name))}${name === active ? ' <span class="chip lav plain">live</span>' : ""}</td><td>${scoreBar(s, 110)}</td><td class="right">${would ? decChip(would) : ""}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function featuresHtml(f) {
    const rows = [
      ["Amount ÷ card average", f.amt_to_card_mean == null ? "new card" : f.amt_to_card_mean.toFixed(1) + "×"],
      ["Card's average spend", fMoney(f.card_amt_mean, 2)],
      ["Txns in previous hour", fInt(f.txn_count_1h)],
      ["Txns in previous 24h", fInt(f.txn_count_24h)],
      ["Spent in previous 24h", fMoney(f.amt_sum_24h, 2)],
      ["Prior card transactions", fInt(f.card_txn_count)],
      ["Distance to merchant", f.dist_km == null ? "–" : Math.round(f.dist_km) + " km"],
      ["Hour of day", f.hour == null ? "–" : String(f.hour).padStart(2, "0") + ":00" + (f.is_night ? " (night)" : "")],
      ["New merchant for card", f.is_new_merchant ? "yes" : "no"],
      ["Cardholder age", f.age == null ? "–" : Math.round(f.age)],
    ];
    return `<div class="kv">${rows.map(([k, v]) => `<div><span>${k}</span><span>${esc(v)}</span></div>`).join("")}</div>`;
  }

  /* ---------- System ---------- */
  PAGES.system = {
    title: "System health",
    sub: () => "Status of every part of the pipeline",
    auto: true,
    init(v) {
      v.innerHTML = `<section class="grid g-4" id="sys-cards"></section>
        <section class="grid g-2-1">
          <div class="card"><div class="card-head"><div><h2>Dead-letter queue</h2><div class="muted">Events rejected by validation instead of crashing the processor</div></div><span class="chip neutral plain" id="dlq-total"></span></div><div class="table-wrap" id="dlq"></div></div>
          <div class="card"><div class="card-head"><div><h2>Troubleshooting</h2><div class="muted">Run these in the project folder</div></div></div>
            <div style="display:flex;flex-direction:column;gap:10px">
              <div class="small strong">See what is running</div><pre class="cmd">docker compose ps</pre>
              <div class="small strong">Start / restart everything</div><pre class="cmd">docker compose up -d</pre>
              <div class="small strong">Logs of one service</div><pre class="cmd">docker compose logs processor --tail 50</pre>
              <div class="small strong">Fresh start (wipes stored data)</div><pre class="cmd">docker compose down -v
docker compose up -d</pre>
            </div></div>
        </section>`;
    },
    async load() {
      await loadStatus();
      const st = S.status;
      if (!st) { $("#sys-cards").innerHTML = `<div class="card" style="grid-column:1/-1">${errorBox({ message: "Dashboard server unreachable" })}</div>`; return; }
      const card = (title, ic, ok, stateText, body) => `<div class="card svc"><div class="svc-head"><span class="kpi-icon ${ok === true ? "ic-mint" : ok === false ? "ic-coral" : "ic-amber"}">${icon(ic)}</span><h2>${title}</h2>
        <span class="svc-state chip ${ok === true ? "approve" : ok === false ? "block" : "review"}">${stateText}</span></div>${body}</div>`;
      const p = st.processor;
      $("#sys-cards").innerHTML = [
        card("Database", "database", st.db.ok, st.db.ok ? "online" : "offline", st.db.ok
          ? `<div class="kv" style="grid-template-columns:1fr"><div><span>Transactions</span><span>${fInt(st.db.transactions)}</span></div><div><span>Alerts</span><span>${fInt(st.db.alerts)}</span></div><div><span>Pending review</span><span>${fInt(st.db.alerts_pending_review)}</span></div><div><span>Last write</span><span>${ago(st.db.last_processed_at)}</span></div></div>`
          : `<div class="small muted">${esc(st.db.error || "")}</div>`),
        card("Feature store", "layers", st.redis.ok, st.redis.ok ? "online" : "offline", `<div class="small muted">${st.redis.ok ? "Redis holds each card's recent history (7-day windows, merchants) and the live-model setting." : esc(st.redis.error || "")}</div>`),
        card("Processor", "activity", p.ok ? true : st.redis.ok ? null : false, p.ok ? "running" : "not running", p.ts
          ? `<div class="kv" style="grid-template-columns:1fr"><div><span>Last heartbeat</span><span>${Math.round(p.age_s)}s ago</span></div><div><span>Processed (this run)</span><span>${fInt(p.processed)}</span></div><div><span>Alerts / invalid / duplicates</span><span>${fInt(p.alerts)} / ${fInt(p.invalid)} / ${fInt(p.duplicates)}</span></div><div><span>Shadow scoring</span><span>${p.shadow ? "on" : "off"}</span></div></div>`
          : `<div class="small muted">${esc(p.error || "No heartbeat.")} Start it with <code>docker compose up -d processor</code>.</div>`),
        card("Models", "cpu", st.models.loaded.length ? true : false, `${st.models.loaded.length} loaded`, `<div class="kv" style="grid-template-columns:1fr"><div><span>Live</span><span>${esc(mLabel(st.models.active))}</span></div><div><span>Default</span><span>${esc(mLabel(st.models.default))}</span></div>
          <div><span>Loaded</span><span>${st.models.loaded.map(mLabel).map(esc).join(", ") || "none"}</span></div></div>`),
      ].join("");
      const r = await api("/api/dead-letters?limit=50");
      if (!r.ok) { $("#dlq").innerHTML = errorBox(r); return; }
      $("#dlq-total").textContent = `${fInt(r.data.total)} total`;
      $("#dlq").innerHTML = r.data.items.length ? `<table class="tbl"><thead><tr><th>When</th><th>Error</th><th>Payload</th></tr></thead><tbody>${r.data.items.map((x) => `<tr><td class="small nowrap">${fDateTime(x.created_at)}</td><td><span class="chip block plain">${esc(x.error)}</span></td><td class="mono small reason-line" title="${esc(x.payload)}">${esc(x.payload)}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty">${icon("check")}<div>No rejected events</div></div>`;
    },
  };

  /* -------------------------------------------------------------- drawer ---- */
  function openDrawer(title) {
    $("#drawer-title").textContent = title;
    $("#drawer-body").innerHTML = '<div class="skeleton" style="height:300px"></div>';
    $("#drawer").classList.remove("hidden"); $("#scrim").classList.remove("hidden");
    $("#drawer").setAttribute("aria-hidden", "false");
    $("#drawer-close").focus();
  }
  function closeDrawer() {
    $("#drawer").classList.add("hidden"); $("#scrim").classList.add("hidden");
    $("#drawer").setAttribute("aria-hidden", "true");
  }

  async function openAlert(id) {
    openDrawer("Alert details");
    const [r, cat] = await Promise.all([api(`/api/alerts/${encodeURIComponent(id)}`), loadCatalog()]);
    if (!r.ok) { $("#drawer-body").innerHTML = errorBox(r); return; }
    const a = r.data;
    const thr = (cat[a.model_name] || {}).thresholds || { review: 0.5, block: 0.9 };
    const col = a.decision === "BLOCK" ? "--coral" : a.decision === "REVIEW" ? "--amber" : "--mint";
    $("#drawer-body").innerHTML = `
      <div class="card" style="box-shadow:var(--inset);display:flex;gap:16px;align-items:center;flex-wrap:wrap">
        <div id="dr-gauge"></div>
        <div style="flex:1;min-width:160px"><div style="display:flex;gap:8px;align-items:center">${decChip(a.decision)} ${truthChip(a.is_fraud)}</div>
          <div style="font-size:26px;font-weight:800;margin-top:6px" class="num">${fMoney(a.amt, 2)}</div>
          <div class="cell-main">${esc(a.merchant)}${appChip(a.trans_id)}</div><div class="muted small">${esc(a.category)} · card ****${esc(a.card_last4)}</div></div>
      </div>
      <div class="kv"><div><span>Event time (UTC)</span><span>${fEvent(a.event_ts)}</span></div><div><span>Processed</span><span>${fDateTime(a.processed_at)}</span></div>
        <div><span>Decided by</span><span>${esc(mLabel(a.model_name))}</span></div><div><span>Scoring time</span><span>${fMs(a.scoring_ms)}</span></div>
        <div><span>Transaction id</span><span class="mono small" title="${esc(a.trans_id)}">${esc(a.trans_id.length > 22 ? a.trans_id.slice(0, 20) + "…" : a.trans_id)}</span></div><div><span>End-to-end</span><span>${fMs(a.e2e_ms)}</span></div></div>
      <div><div class="section-title">Why it was flagged</div>${reasonsHtml(a.reasons, a.decision)}</div>
      <div><div class="section-title">What every model thought</div>${shadowHtml(a.shadow_scores, cat, a.model_name)}</div>
      <div><div class="section-title">Key features</div>${featuresHtml(a.features || {})}</div>
      <div class="card" style="box-shadow:var(--inset)"><div class="section-title">Analyst review</div>
        <div style="margin-bottom:12px">Current: ${reviewChip(a.analyst_label)} ${a.reviewed_at ? `<span class="muted small">· ${fDateTime(a.reviewed_at)}</span>` : ""}</div>
        <div class="label-actions"><button class="btn coral" data-label="1">${icon("alert")}Confirm fraud</button><button class="btn mint" data-label="0">${icon("check")}Mark legitimate</button>
          ${a.analyst_label != null ? '<button class="btn" data-label="null">Clear label</button>' : ""}</div>
        <div class="muted small" style="margin-top:10px">Labels are stored for retraining (feedback loop).</div></div>`;
    C.gauge($("#dr-gauge"), { value: a.score, color: col, label: fScore(a.score), size: 170, marks: [{ at: thr.review, color: "--amber" }, { at: thr.block, color: "--coral" }] });
    $$("[data-label]").forEach((b) => (b.onclick = async () => {
      const label = b.dataset.label === "null" ? null : Number(b.dataset.label);
      b.disabled = true;
      const res = await api(`/api/alerts/${encodeURIComponent(id)}/label`, { method: "POST", body: JSON.stringify({ label }) });
      if (res.ok) { toast(label === 1 ? "Marked as fraud" : label === 0 ? "Marked as legitimate" : "Label cleared", "ok"); loadStatus(); refreshPage(); openAlert(id); }
      else { b.disabled = false; toast(res.message, "bad"); }
    }));
  }

  function openTxn(t) {
    if (!t) return;
    openDrawer("Transaction");
    $("#drawer-body").innerHTML = `<div class="card" style="box-shadow:var(--inset)"><div style="display:flex;gap:8px">${decChip(t.decision)} ${truthChip(t.is_fraud)}</div>
      <div style="font-size:26px;font-weight:800;margin-top:6px" class="num">${fMoney(t.amt, 2)}</div><div class="cell-main">${esc(t.merchant)}${appChip(t.trans_id)}</div><div class="muted small">${esc(t.category)} · card ****${esc(t.card_last4)}</div></div>
      <div class="kv"><div><span>Score</span><span>${fScore(t.score)}</span></div><div><span>Decided by</span><span>${esc(mLabel(t.model_name))}</span></div>
      <div><span>Event time (UTC)</span><span>${fEvent(t.event_ts)}</span></div><div><span>Processed</span><span>${fDateTime(t.processed_at)}</span></div>
      <div><span>Scoring time</span><span>${fMs(t.scoring_ms)}</span></div><div><span>Transaction id</span><span class="mono small" title="${esc(t.trans_id)}">${esc(t.trans_id.length > 22 ? t.trans_id.slice(0, 20) + "…" : t.trans_id)}</span></div></div>
      <div class="muted small">Approved transactions are stored without reason codes. Try it in the <a href="#/score">Score tester</a> to see the full breakdown.</div>`;
  }

  /* --------------------------------------------------------------- admin ---- */
  function setAdmin(a) {
    S.admin = a;
    if (a) localStorage.setItem("sl-admin", JSON.stringify(a)); else localStorage.removeItem("sl-admin");
    $("#admin-label").textContent = a ? `${a.name} · Log out` : "Admin login";
    $("#admin-btn").innerHTML = `${icon(a ? "user" : "lock")}<span id="admin-label">${a ? esc(a.name) + " · Log out" : "Admin login"}</span>`;
  }
  function openLogin() {
    if (S.status && S.status.admin_enabled === false) { toast("Admin is disabled: set ADMIN_PASSWORD in .env and restart.", "bad"); return; }
    $("#login-error").textContent = "";
    $("#login-form").reset();
    $("#login-modal").classList.remove("hidden");
    $("#login-form").elements.name.focus();
  }
  function closeLogin() { $("#login-modal").classList.add("hidden"); }

  /* -------------------------------------------------------------- router ---- */
  async function route() {
    const [page, query] = (location.hash.replace("#/", "") || "overview").split("?");
    S.page = PAGES[page] ? page : "overview";
    const P = PAGES[S.page];
    if (query && P.f) {  // e.g. #/transactions?q=TXN-20201231-AB12CD34 (link from the payment app receipt)
      const qp = new URLSearchParams(query);
      Object.assign(P.f, { q: "", decision: "", category: "", truth: "", review: "", model: "", offset: 0 });
      qp.forEach((val, key) => { if (key in P.f) P.f[key] = val; });
    }
    $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === S.page));
    $("#page-title").textContent = P.title;
    $("#page-sub").textContent = P.sub();
    $("#scope-seg").classList.toggle("hidden", !P.scope);
    $("#sidebar").classList.remove("open");
    closeDrawer();
    document.title = `${P.title} · Securelytics`;
    const v = $("#view");
    v.innerHTML = "";
    await P.init(v);
    paintIcons(v);
    await refreshPage();
    v.focus({ preventScroll: true });
  }

  async function refreshPage() {
    if (S.busy) return;
    S.busy = true;
    try {
      await loadStatus();
      const P = PAGES[S.page];
      $("#page-sub").textContent = P.sub();
      await P.load();
      paintIcons($("#view"));
      $("#updated").textContent = new Date().toLocaleTimeString();
    } finally { S.busy = false; }
  }

  function schedule() {
    clearInterval(S.timer);
    if (S.refresh > 0) S.timer = setInterval(() => {
      const busyUI = !$("#drawer").classList.contains("hidden") || !$("#login-modal").classList.contains("hidden");
      if (!document.hidden && !busyUI && PAGES[S.page].auto) refreshPage();
    }, S.refresh * 1000);
  }

  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("sl-theme", t);
    $$("[data-theme-set]").forEach((b) => b.classList.toggle("on", b.dataset.themeSet === t));
    C.rerenderAll();
  }

  /* ---------------------------------------------------------------- boot ---- */
  function boot() {
    paintIcons();
    applyTheme(document.documentElement.getAttribute("data-theme") || "light");
    $$("[data-theme-set]").forEach((b) => (b.onclick = () => applyTheme(b.dataset.themeSet)));
    $$("#scope-seg button").forEach((b) => {
      b.classList.toggle("on", b.dataset.scope === S.scope);
      b.onclick = () => { S.scope = b.dataset.scope; localStorage.setItem("sl-scope", S.scope); $$("#scope-seg button").forEach((x) => x.classList.toggle("on", x === b)); refreshPage(); };
    });
    $("#refresh-sel").value = String(S.refresh);
    $("#refresh-sel").onchange = (e) => { S.refresh = Number(e.target.value); localStorage.setItem("sl-refresh", S.refresh); schedule(); };
    $("#refresh-btn").onclick = async () => { $("#refresh-btn").classList.add("pressed"); await refreshPage(); $("#refresh-btn").classList.remove("pressed"); };
    $("#menu-btn").onclick = () => $("#sidebar").classList.toggle("open");
    $("#drawer-close").onclick = closeDrawer;
    $("#scrim").onclick = closeDrawer;
    $("#admin-btn").onclick = async () => {
      if (S.admin) { await api("/api/admin/logout", { method: "POST" }); setAdmin(null); toast("Logged out", "ok"); if (S.page === "models") PAGES.models.load(); }
      else openLogin();
    };
    $("#login-cancel").onclick = closeLogin;
    $("#login-modal").onclick = (e) => { if (e.target.id === "login-modal") closeLogin(); };
    $("#login-form").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const r = await api("/api/admin/login", { method: "POST", body: JSON.stringify({ name: fd.get("name"), password: fd.get("password") }) });
      if (!r.ok) { $("#login-error").textContent = r.message; return; }
      setAdmin({ token: r.data.token, name: r.data.name });
      closeLogin();
      toast(`Welcome, ${r.data.name}. You can now switch models.`, "ok");
      if (S.page === "models") PAGES.models.load(); else location.hash = "#/models";
    };
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); closeLogin(); } });
    setAdmin(S.admin);
    if (S.admin) api("/api/admin/me").then((r) => { if (r.ok && !r.data.admin) setAdmin(null); });
    window.addEventListener("hashchange", route);
    schedule();
    route();
  }
  boot();
})();
