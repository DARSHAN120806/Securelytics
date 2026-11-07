/* Securelytics Bank payment simulator. The customer only ever sees "Payment successful";
   the fraud decision is made by the trained model in the backend and shown on the admin dashboard. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])));
  const ICON = {
    check: '<polyline points="20 6 9 17 4 12"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="3"/><line x1="2" y1="10" x2="22" y2="10"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  };
  const icon = (n) => `<span class="ico"><svg viewBox="0 0 24 24" aria-hidden="true">${ICON[n]}</svg></span>`;
  const money = (v) => "$" + Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtWhen = (s) => (s ? new Date(s + ":00Z").toLocaleString([], { timeZone: "UTC", weekday: "short", month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "–");
  const MERCHANTS = {
    grocery_pos: ["FreshMart", "Green Basket Grocers"], grocery_net: ["CartNow Groceries", "FarmBox Delivery"],
    shopping_pos: ["City Outfitters", "Home & Style"], shopping_net: ["ShopZone Online", "GadgetHub.com"],
    gas_transport: ["QuickFuel", "Metro Transit"], food_dining: ["Luigi's Trattoria", "Sunrise Diner"],
    entertainment: ["Starlight Cinemas", "Arena Tickets"], health_fitness: ["Peak Fitness", "CarePlus Pharmacy"],
    home: ["HomeBase Hardware", "Cozy Furnishings"], kids_pets: ["Paws & Claws", "Little Steps Toys"],
    personal_care: ["Glow Salon", "Daily Essentials"], travel: ["SkyWay Airlines", "Harbor Hotel"],
    misc_pos: ["Corner Store", "Main St. Market"], misc_net: ["Digital Goods Co", "WebPay Services"],
  };

  const S = { cards: [], categories: {}, cities: [], card: null };
  const store = {
    get card() { return localStorage.getItem("sl-pay-card"); },
    set card(v) { v ? localStorage.setItem("sl-pay-card", v) : localStorage.removeItem("sl-pay-card"); },
    history(id) { try { return JSON.parse(localStorage.getItem("sl-pay-hist-" + id) || "[]"); } catch (e) { return []; } },
    push(id, r) { const h = [r, ...this.history(id)].slice(0, 8); localStorage.setItem("sl-pay-hist-" + id, JSON.stringify(h)); },
  };

  async function api(path, opts = {}) {
    try {
      const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json" } });
      const data = await res.json().catch(() => ({}));
      return res.ok ? { ok: true, data } : { ok: false, message: data.message || res.statusText };
    } catch (e) { return { ok: false, message: "Cannot reach the bank. Is the 'web' container running?" }; }
  }
  function toast(msg, kind = "") {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.innerHTML = `${icon(kind === "bad" ? "alert" : "check")}<span>${esc(msg)}</span>`;
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }

  const cardHtml = (c) => `<div class="bank-card c${c.color}">
      <span class="bc-circles"></span><span class="bc-circles two"></span>
      <div class="bc-top"><span class="bc-bank">SECURELYTICS</span><span class="bc-type">DEBIT</span></div>
      <div class="bc-row"><span class="bc-chip"></span><span class="bc-wave"><svg viewBox="0 0 24 24"><path d="M8 7a7 7 0 0 1 0 10"/><path d="M12 4a11 11 0 0 1 0 16"/><path d="M4 10a3 3 0 0 1 0 4"/></svg></span></div>
      <div class="bc-number">•••• •••• •••• ${esc(c.last4)}</div>
      <div class="bc-bottom"><div><div class="bc-label">CARDHOLDER</div><div class="bc-holder">${esc(c.holder)}</div></div>
        <div><div class="bc-label" style="text-align:right">HOME</div><div class="bc-home">${esc(c.home)}</div></div></div>
    </div>`;

  async function loadCards() {
    const r = await api("/api/pay/cards");
    if (!r.ok) return r;
    S.cards = r.data.cards; S.categories = r.data.categories; S.cities = r.data.cities;
    if (S.card) S.card = S.cards.find((c) => c.id === S.card.id) || null;
    return r;
  }

  /* ---------------- view 1: choose a card ---------------- */
  async function showPicker() {
    store.card = null; S.card = null;
    $("#switch-card").classList.add("hidden");
    const v = $("#pay-view");
    v.innerHTML = '<div class="skeleton" style="height:260px"></div>';
    const r = await loadCards();
    if (!r.ok) { v.innerHTML = errorCard(r.message); return; }
    v.innerHTML = `<div><div class="hero-title">Choose your card</div>
        <div class="muted">Pick a cardholder to pay as. In this demo the card is your login.</div></div>
      <div class="cards-grid">${S.cards.map((c) => `<button class="card-pick" data-id="${c.id}" aria-label="Use card ending ${c.last4}, ${esc(c.holder)}">${cardHtml(c)}</button>`).join("")}</div>`;
    $$(".card-pick").forEach((b) => (b.onclick = () => { store.card = b.dataset.id; showCard(); }));
    v.focus({ preventScroll: true });
  }

  function errorCard(msg) {
    return `<div class="card"><div class="empty">${icon("alert")}<div class="strong">${esc(msg)}</div>
      <div class="small" style="margin-top:6px">Start the stack with <code>docker compose up -d</code> and make sure <code>data/raw/fraudTest.csv</code> exists.</div>
      <button class="btn" style="margin-top:14px" onclick="location.reload()">${icon("refresh")}Try again</button></div></div>`;
  }

  /* ---------------- view 2: card home + pay ---------------- */
  const addMinutes = (s, m) => { const d = new Date(s + ":00Z"); d.setUTCMinutes(d.getUTCMinutes() + m); return d.toISOString().slice(0, 16); };
  const nextTwoAm = (s) => { const d = new Date(s + ":00Z"); d.setUTCDate(d.getUTCDate() + (d.getUTCHours() >= 2 ? 1 : 0)); d.setUTCHours(2, 0, 0, 0); return d.toISOString().slice(0, 16); };
  const baseTime = () => (S.card && S.card.last_activity) || "2020-12-31T12:00";
  const newTxnId = (when) => "TXN-" + when.slice(0, 10).replace(/-/g, "") + "-" + Math.random().toString(16).slice(2, 10).toUpperCase();

  async function showCard() {
    const v = $("#pay-view");
    if (!S.cards.length) { const r = await loadCards(); if (!r.ok) { v.innerHTML = errorCard(r.message); return; } }
    S.card = S.cards.find((c) => c.id === store.card);
    if (!S.card) return showPicker();
    $("#switch-card").classList.remove("hidden");
    const c = S.card;
    v.innerHTML = `<div class="pay-layout">
      <div class="side-col">
        ${cardHtml(c)}
        <div class="card"><div class="card-head" style="margin-bottom:10px"><h2>Card details</h2><span class="chip approve">active</span></div>
          <div class="info-list"><div><span>Cardholder</span><span>${esc(c.holder)}</span></div><div><span>Card</span><span class="mono">•••• ${esc(c.last4)}</span></div>
          <div><span>Home</span><span>${esc(c.home)}</span></div><div><span>Last transaction</span><span id="last-act">${fmtWhen(c.last_activity)}</span></div></div></div>
        <div class="card"><div class="card-head" style="margin-bottom:10px"><h2>Recent payments</h2><span class="muted small">made in this app</span></div><div class="history" id="history"></div></div>
      </div>
      <form class="card" id="pay-form" novalidate>
        <div class="card-head"><div><h2>Make a payment</h2><div class="muted">Paying with card •••• ${esc(c.last4)}</div></div>${icon("lock")}</div>
        <div style="display:flex;flex-direction:column;gap:16px">
          <label class="field">Amount<div class="amount-field"><span>$</span><input name="amount" type="number" inputmode="decimal" min="0.01" max="25000" step="0.01" placeholder="0.00" required></div></label>
          <div class="form-grid">
            <label class="field">Category<div class="select-box"><select class="input select" name="category">${Object.entries(S.categories).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join("")}</select></div></label>
            <label class="field">Merchant<input class="input" name="merchant" list="merchant-list" maxlength="60" required placeholder="Store name"><datalist id="merchant-list"></datalist></label>
            <label class="field">Location<div class="select-box"><select class="input select" name="location"><option value="home">Near home · ${esc(c.home)}</option>${S.cities.map((x) => `<option>${esc(x)}</option>`).join("")}</select></div></label>
            <label class="field">Date &amp; time (UTC)<input class="input" name="when" type="datetime-local" required>
              <div class="quick"><button type="button" class="btn small" data-when="soon">In 15 min</button><button type="button" class="btn small" data-when="evening">This evening 7 PM</button><button type="button" class="btn small" data-when="night">2:00 AM</button></div></label>
          </div>
          <label class="field">Transaction ID <span class="faint" style="font-weight:500">(auto-generated, optional)</span>
            <div class="txn-row"><input class="input mono" name="txn_id" maxlength="40"><button type="button" class="btn icon-btn" id="new-id" title="New ID" aria-label="Generate new transaction ID">${icon("refresh")}</button></div></label>
          <div class="hint">Simulation clock: this card's history comes from the replayed 2020 data, so payments are dated after its last transaction (${fmtWhen(c.last_activity)}).</div>
          <div class="form-error" id="pay-error"></div>
          <button type="submit" class="btn primary pay-btn" id="pay-btn">Pay</button>
        </div>
      </form></div>`;
    const f = $("#pay-form");
    const setWhen = (w) => { f.when.value = w; f.txn_id.value = newTxnId(w); };
    const fillMerchants = () => { $("#merchant-list").innerHTML = (MERCHANTS[f.category.value] || []).map((m) => `<option value="${esc(m)}">`).join(""); };
    f.category.value = "grocery_pos"; fillMerchants(); f.merchant.value = MERCHANTS.grocery_pos[0];
    setWhen(addMinutes(baseTime(), 15));
    f.category.onchange = () => { fillMerchants(); f.merchant.value = (MERCHANTS[f.category.value] || [""])[0]; };
    const updateBtn = () => { const a = Number(f.amount.value); $("#pay-btn").textContent = a > 0 ? `Pay ${money(a)}` : "Pay"; };
    f.amount.oninput = updateBtn;
    f.addEventListener("input", () => ($("#pay-error").textContent = ""));
    f.addEventListener("change", () => ($("#pay-error").textContent = ""));
    $$("[data-when]").forEach((b) => (b.onclick = () => {
      const base = baseTime();
      const w = b.dataset.when === "soon" ? addMinutes(base, 15) : b.dataset.when === "night" ? nextTwoAm(base)
        : (() => { const d = new Date(base + ":00Z"); if (d.getUTCHours() >= 19) d.setUTCDate(d.getUTCDate() + 1); d.setUTCHours(19, 0, 0, 0); return d.toISOString().slice(0, 16); })();
      setWhen(w);
    }));
    $("#new-id").onclick = () => (f.txn_id.value = newTxnId(f.when.value || baseTime()));
    f.onsubmit = async (e) => {
      e.preventDefault();
      $("#pay-error").textContent = "";
      const bad = [f.amount, f.merchant, f.when].filter((i) => !i.checkValidity());
      if (bad.length) { $("#pay-error").textContent = "Please check: " + bad.map((i) => ({ amount: "amount", merchant: "merchant", when: "date & time" }[i.name])).join(", "); bad[0].focus(); return; }
      const body = { card_id: c.id, amount: Number(f.amount.value), category: f.category.value, merchant: f.merchant.value.trim(), location: f.location.value, when: f.when.value, txn_id: f.txn_id.value.trim() };
      const btn = $("#pay-btn"); btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Processing payment…';
      const r = await api("/api/pay", { method: "POST", body: JSON.stringify(body) });
      btn.disabled = false; updateBtn();
      if (!r.ok) {
        $("#pay-error").textContent = r.message;
        if (/last transaction/.test(r.message)) { await loadCards(); S.card = S.cards.find((x) => x.id === c.id); $("#last-act").textContent = fmtWhen(S.card.last_activity); }
        return;
      }
      store.push(c.id, r.data);
      showReceipt(r.data);
      f.amount.value = ""; updateBtn();
      setTimeout(async () => { await loadCards(); S.card = S.cards.find((x) => x.id === c.id) || S.card; if ($("#last-act")) $("#last-act").textContent = fmtWhen(S.card.last_activity); }, 2500);
      renderHistory();
    };
    renderHistory();
  }

  function renderHistory() {
    const h = store.history(S.card.id);
    $("#history").innerHTML = h.length ? h.map((p) => `<div class="history-item"><span class="hi-icon">${icon("check")}</span>
        <div style="min-width:0"><div class="cell-main" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(p.merchant)}</div><div class="cell-sub">${fmtWhen(p.when)} · ${esc(p.location)}</div></div>
        <div class="right"><div class="strong num">${money(p.amount)}</div><div class="cell-sub">Completed</div></div></div>`).join("")
      : '<div class="muted small">No payments yet.</div>';
  }

  function showReceipt(r) {
    $("#receipt").innerHTML = `<div class="ok-badge">${icon("check")}</div>
      <div><h2 id="receipt-title">Payment successful</h2><div class="muted small">Thank you, ${esc(r.holder.split(" ")[0])}</div></div>
      <div class="r-amount">${money(r.amount)}</div>
      <div class="info-list"><div><span>Merchant</span><span>${esc(r.merchant)}</span></div><div><span>Category</span><span>${esc(r.category_label)}</span></div>
        <div><span>Location</span><span>${esc(r.location)}</span></div><div><span>Date &amp; time</span><span>${fmtWhen(r.when)}</span></div>
        <div><span>Card</span><span class="mono">•••• ${esc(r.card_last4)}</span></div><div><span>Transaction ID</span><span class="mono small">${esc(r.txn_id)}</span></div>
        <div><span>Status</span><span style="color:var(--mint-ink)">Completed</span></div></div>
      <div class="row-end" style="justify-content:center"><button class="btn primary" id="receipt-done">Done</button></div>
      <div class="demo-link">Demo: the bank's fraud system scored this payment in the background.
        <a href="/#/transactions?q=${encodeURIComponent(r.txn_id)}" target="_blank" rel="noopener">See it on the admin dashboard ↗</a></div>`;
    $("#receipt-modal").classList.remove("hidden");
    $("#receipt-done").focus();
    $("#receipt-done").onclick = closeReceipt;
  }
  function closeReceipt() { $("#receipt-modal").classList.add("hidden"); }

  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("sl-theme", t);
    $$("[data-theme-set]").forEach((b) => b.classList.toggle("on", b.dataset.themeSet === t));
  }

  applyTheme(document.documentElement.getAttribute("data-theme") || "light");
  $$("[data-theme-set]").forEach((b) => (b.onclick = () => applyTheme(b.dataset.themeSet)));
  $("#switch-card").onclick = showPicker;
  $("#receipt-modal").onclick = (e) => { if (e.target.id === "receipt-modal") closeReceipt(); };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeReceipt(); });
  if (store.card) showCard(); else showPicker();
})();
