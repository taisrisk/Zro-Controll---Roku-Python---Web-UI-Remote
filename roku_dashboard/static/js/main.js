function qs(sel, root = document) {
  return root.querySelector(sel);
}

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function getActiveIp() {
  return localStorage.getItem("zrocontrol.ip") || "";
}

function setActiveIp(ip) {
  localStorage.setItem("zrocontrol.ip", ip);
}

function syncIpFromQuery() {
  const u = new URL(window.location.href);
  const ip = (u.searchParams.get("ip") || "").trim();
  if (ip) setActiveIp(ip);
}

function showToast(message, kind = "info") {
  const toast = qs("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.remove("hidden");
  toast.style.borderColor =
    kind === "error" ? "rgba(255,120,150,0.28)" : "rgba(255,255,255,0.12)";
  window.clearTimeout(showToast._t);
  showToast._t = window.setTimeout(() => toast.classList.add("hidden"), 1800);
}

function isTypingTarget(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || el.isContentEditable;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function postOk(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return;
  const data = await res.json().catch(() => ({}));
  throw new Error(data.error || `Request failed (${res.status})`);
}

function wireNavIpLinks() {
  const ip = getActiveIp();
  qsa(".js-nav-ip").forEach((a) => {
    const base = a.dataset.path || a.getAttribute("href");
    if (!ip) {
      a.setAttribute("href", base);
      return;
    }
    const u = new URL(base, window.location.origin);
    u.searchParams.set("ip", ip);
    a.setAttribute("href", u.pathname + u.search);
  });
}

function wireDeviceSelect() {
  qsa(".js-select-device").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", () => {
      const ip = btn.dataset.ip || "";
      if (!ip) return;
      setActiveIp(ip);
      showToast(`Selected ${ip}`);
      wireNavIpLinks();
      renderActiveDeviceHighlight();
    });
  });
}

function renderActiveDeviceHighlight() {
  const ip = getActiveIp();
  qsa(".device-card[data-ip]").forEach((row) => {
    row.classList.toggle("is-active", !!ip && row.dataset.ip === ip);
  });
}

function wireManualIp() {
  const setBtn = qs("#setIpBtn");
  const input = qs("#manualIp");
  if (!setBtn || !input) return;
  setBtn.addEventListener("click", () => {
    const ip = (input.value || "").trim();
    if (!ip) return;
    setActiveIp(ip);
    showToast(`Selected ${ip}`);
    wireNavIpLinks();
  });
}

function setControlsDisabled(disabled) {
  qsa(".js-send, .js-launch, .js-refresh-channels").forEach((el) => {
    if (disabled) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
}

async function gateControlsByReachability() {
  const ip = getActiveIp();
  if (!ip) return;
  const hasControls = qsa(".js-send, .js-launch, .js-refresh-channels").length > 0;
  if (!hasControls) return;

  try {
    const u = new URL("/api/reachable", window.location.origin);
    u.searchParams.set("ip", ip);
    const res = await fetch(u, { cache: "no-store" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || "Reachability check failed");
    if (data.reachable === false) {
      setControlsDisabled(true);
      showToast("Device unreachable on this network", "error");
    } else {
      setControlsDisabled(false);
    }
  } catch (err) {
    setControlsDisabled(true);
  }
}

function wireRemoteButtons() {
  qsa(".js-send").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    if (btn.dataset.hold === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async () => {
      const key = btn.dataset.key;
      const ip = getActiveIp();
      if (!ip) return showToast("Select a device first", "error");
      try {
        await postOk("/api/keypress", { ip, key });
        showToast(key);
        btn.classList.add("is-pressed");
        window.setTimeout(() => btn.classList.remove("is-pressed"), 160);
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

function wireRemoteHoldRepeat() {
  qsa('.js-send[data-hold="1"]').forEach((btn) => {
    if (btn.dataset.holdWired === "1") return;
    btn.dataset.holdWired = "1";
    let interval = null;

    const start = async () => {
      if (btn.disabled) return;
      const key = btn.dataset.key;
      const ip = getActiveIp();
      if (!ip) return showToast("Select a device first", "error");
      try {
        await postOk("/api/keypress", { ip, key });
        btn.classList.add("is-pressed");
        window.setTimeout(() => btn.classList.remove("is-pressed"), 140);
      } catch (err) {
        showToast(err.message, "error");
      }
      interval = window.setInterval(async () => {
        try {
          await postOk("/api/keypress", { ip, key });
        } catch (err) {
          showToast(err.message, "error");
          stop();
        }
      }, 150);
    };

    const stop = () => {
      if (interval) window.clearInterval(interval);
      interval = null;
    };

    btn.addEventListener("pointerdown", (e) => {
      if (btn.disabled) return;
      if (e.button !== 0) return;
      e.preventDefault();
      stop();
      start();
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) =>
      btn.addEventListener(ev, () => stop())
    );
  });
}

function wireLaunchButtons() {
  qsa(".js-launch").forEach((btn) => {
    if (btn.dataset.wired === "1") return;
    btn.dataset.wired = "1";
    btn.addEventListener("click", async () => {
      const appId = btn.dataset.appId;
      const appName = btn.dataset.appName || btn.textContent || "";
      const ip = getActiveIp();
      if (!ip) return showToast("Select a device first", "error");
      try {
        await postOk("/api/launch", { ip, app_id: appId, app_name: appName.trim() });
        showToast("Launch");
        btn.classList.add("is-pressed");
        window.setTimeout(() => btn.classList.remove("is-pressed"), 180);
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

function wireAppCardLaunch() {
  qsa(".app-card").forEach((card) => {
    if (card.dataset.wiredCard === "1") return;
    card.dataset.wiredCard = "1";
    card.addEventListener("click", async (e) => {
      if (e.target.closest("button, a, input")) return;
      const appId = card.dataset.id;
      const appName = card.dataset.appName || "";
      const ip = getActiveIp();
      if (!ip) return showToast("Select a device first", "error");
      try {
        await postOk("/api/launch", { ip, app_id: appId, app_name: appName.trim() });
        showToast("Launch");
        card.classList.add("is-pressed");
        window.setTimeout(() => card.classList.remove("is-pressed"), 180);
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });
}

function wireChannelSearch() {
  const input = qs("#channelSearch");
  const grid = qs("#channelGrid");
  if (!input || !grid) return;

  const cards = qsa(".app-card", grid);
  input.addEventListener("input", () => {
    const q = (input.value || "").trim().toLowerCase();
    cards.forEach((card) => {
      const name = card.dataset.name || "";
      card.style.display = !q || name.includes(q) ? "" : "none";
    });
  });
}

function wireRefreshChannels() {
  const btn = qs(".js-refresh-channels");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const ip = getActiveIp();
    if (!ip) return showToast("Select a device first", "error");
    const u = new URL("/channels", window.location.origin);
    u.searchParams.set("ip", ip);
    window.location.href = u.pathname + u.search;
  });
}

async function fetchLanDevices(timeoutS) {
  const u = new URL("/lan/devices", window.location.origin);
  if (timeoutS) u.searchParams.set("timeout", String(timeoutS));
  const res = await fetch(u, { cache: "no-store" });
  if (!res.ok) throw new Error(`Discovery failed (${res.status})`);
  return res.json();
}

const _lanMissingCounts = new Map();

function _cssEscape(s) {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(s);
  return String(s).replace(/"/g, '\\"');
}

function _deviceEl(ip) {
  return qs(`.device-card[data-ip="${_cssEscape(ip)}"]`);
}

function _upsertDeviceCard(d) {
  const list = qs("#deviceList");
  if (!list) return;
  qs(".lan-empty", list)?.remove();
  const ip = String(d.ip || "").trim();
  if (!ip) return;

  const name = String(d.name || "Roku");
  const model = String(d.model || "");
  const iconUrl = String(d.icon_url || "");
  const reachable = d.reachable !== false;

  let el = _deviceEl(ip);
  const active = getActiveIp() === ip;
  if (!el) {
    const html = `
      <div class="device-card${active ? " is-active" : ""}${reachable ? "" : " is-unreachable"}" data-ip="${escapeHtml(ip)}">
        <div class="device-ic" aria-hidden="true">
          ${iconUrl ? `<img src="${escapeHtml(iconUrl)}" alt="" loading="lazy" onerror="this.remove()" />` : ""}
        </div>
        <div class="min-w-0">
          <div class="font-semibold truncate device-name">${escapeHtml(name)}</div>
          <div class="text-xs muted font-mono truncate device-meta">${escapeHtml(ip)}${model ? ` • ${escapeHtml(model)}` : ""}</div>
          <div class="device-actions">
            <button class="cta js-select-device" data-ip="${escapeHtml(ip)}">Select</button>
            <a class="button" href="/channels?ip=${escapeHtml(ip)}">Channels</a>
            <a class="button" href="/remote?ip=${escapeHtml(ip)}">Remote</a>
          </div>
        </div>
      </div>
    `;
    list.insertAdjacentHTML("beforeend", html);
    el = _deviceEl(ip);
    wireDeviceSelect();
  } else {
    el.classList.toggle("is-unreachable", !reachable);
    el.classList.remove("is-stale");
    const nameEl = qs(".device-name", el);
    const metaEl = qs(".device-meta", el);
    if (nameEl) nameEl.textContent = name;
    if (metaEl) metaEl.textContent = model ? `${ip} • ${model}` : ip;
    const img = qs("img", el);
    if (iconUrl && !img) {
      qs(".device-ic", el)?.insertAdjacentHTML(
        "beforeend",
        `<img src="${escapeHtml(iconUrl)}" alt="" loading="lazy" onerror="this.remove()" />`
      );
    }
  }
  _lanMissingCounts.set(ip, 0);
  renderActiveDeviceHighlight();
}

function _markMissingDevices(seenIps) {
  qsa(".device-card[data-ip]").forEach((el) => {
    const ip = el.dataset.ip || "";
    if (!ip || seenIps.has(ip)) return;
    const count = (_lanMissingCounts.get(ip) || 0) + 1;
    _lanMissingCounts.set(ip, count);
    el.classList.add("is-stale");
    if (count >= 3) {
      el.classList.add("is-removing");
      window.setTimeout(() => el.remove(), 180);
    }
  });
}

function startLanAutoRefresh() {
  const list = qs("#deviceList");
  if (!list) return;

  const timeoutS = list.dataset.timeout || "";
  const spinner = qs("#lanSpinner");
  const updated = qs("#lanUpdated");
  let inFlight = false;
  let lastMissing = false;

  const tick = async () => {
    if (inFlight) return;
    inFlight = true;
    spinner?.classList.remove("hidden");
    try {
      const devices = await fetchLanDevices(timeoutS);
      const seen = new Set();
      if (Array.isArray(devices)) {
        devices.forEach((d) => {
          if (!d || !d.ip) return;
          seen.add(String(d.ip));
          _upsertDeviceCard(d);
        });
      }
      _markMissingDevices(seen);
      const ip = getActiveIp();
      const found = !!ip && Array.isArray(devices) && devices.some((d) => (d.ip || "") === ip);
      if (ip && !found && !lastMissing) showToast(`Selected device offline: ${ip}`, "error");
      lastMissing = ip ? !found : false;
      if (updated) updated.textContent = new Date().toLocaleTimeString();
    } catch (err) {
      if (updated) updated.textContent = "error";
    } finally {
      spinner?.classList.add("hidden");
      inFlight = false;
    }
  };

  window.setTimeout(tick, 250);
  window.setInterval(tick, 15000);
}

function wireKeyboardShortcuts() {
  document.addEventListener("keydown", async (e) => {
    if (isTypingTarget(e.target)) return;
    const ip = getActiveIp();
    if (!ip) return;

    const keyMap = {
      ArrowUp: "Up",
      ArrowDown: "Down",
      ArrowLeft: "Left",
      ArrowRight: "Right",
      Enter: "Select",
      " ": "Play",
      Escape: "Back",
      Backspace: "Back",
      Home: "Home",
    };
    const k = keyMap[e.key];
    if (!k) return;
    e.preventDefault();
    try {
      await postOk("/api/keypress", { ip, key: k });
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

async function fetchRecentChannels(ip) {
  const u = new URL("/api/recent-channels", window.location.origin);
  u.searchParams.set("ip", ip);
  const res = await fetch(u, { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Request failed (${res.status})`);
  return data.recent_channels || [];
}

function renderRecentStrip(recentChannels) {
  const strip = qs("#recentStrip");
  if (!strip) return;
  const ip = getActiveIp();
  const items = Array.isArray(recentChannels) ? recentChannels : [];
  const buttons = items
    .slice(0, 10)
    .map((ch) => {
      const id = escapeHtml(ch.id || "");
      const name = escapeHtml(ch.name || ch.id || "");
      const disabled = ip ? "" : "disabled";
      return `<button class="button js-launch" data-app-id="${id}" data-app-name="${name}" ${disabled}>${name}</button>`;
    })
    .join("");
  strip.innerHTML = `<div class="text-xs text-slate-400 uppercase tracking-widest">Recent</div>${buttons || '<div class="text-sm text-slate-300">No recent channels yet.</div>'}`;
  wireLaunchButtons();
}

function startActiveAppPolling() {
  const grid = qs("#channelGrid");
  if (!grid) return;
  const ip = getActiveIp();
  if (!ip) return;

  const tick = async () => {
    try {
      const u = new URL("/api/active-app", window.location.origin);
      u.searchParams.set("ip", ip);
      const res = await fetch(u, { cache: "no-store" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || "active-app failed");
      const recent = await fetchRecentChannels(ip);
      renderRecentStrip(recent);
    } catch (err) {
      // ignore; device may be sleeping/offline
    }
  };

  window.setTimeout(tick, 400);
  window.setInterval(tick, 5000);
}

function fmtDuration(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${ss}s`;
  return `${ss}s`;
}

async function fetchUserData(ip, refresh = false) {
  const u = new URL("/api/user-data", window.location.origin);
  u.searchParams.set("ip", ip);
  if (refresh) u.searchParams.set("refresh", "1");
  const res = await fetch(u, { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || `Request failed (${res.status})`);
  return data.data;
}

function renderUser(data) {
  if (!data) return;
  qs("#userId") && (qs("#userId").textContent = data.user_id || "—");
  qs("#userUpdated") && (qs("#userUpdated").textContent = data.updated_ts || "—");

  const totals = data.totals || {};
  qs("#statToday") && (qs("#statToday").textContent = fmtDuration(totals.today_sec));
  qs("#statWeek") && (qs("#statWeek").textContent = fmtDuration(totals.week_sec));
  qs("#statMonth") && (qs("#statMonth").textContent = fmtDuration(totals.month_sec));
  qs("#statTotal") && (qs("#statTotal").textContent = fmtDuration(totals.total_watch_time_sec));

  const current = data.current;
  qs("#currentApp") && (qs("#currentApp").textContent = current ? (current.channel_name || current.channel_id || "—") : "—");
  qs("#currentStart") && (qs("#currentStart").textContent = current ? (current.start_time || "—") : "—");

  const list = qs("#sessionList");
  if (!list) return;
  const sessions = Array.isArray(data.sessions) ? data.sessions : [];
  if (sessions.length === 0) {
    list.innerHTML = '<div class="muted">No sessions yet. Leave Channels open so the dashboard can track active app changes.</div>';
    return;
  }
  list.innerHTML = sessions.slice(0, 25).map((s) => {
    const name = escapeHtml(s.channel_name || s.channel_id || "—");
    const st = escapeHtml(s.start_time || "");
    const et = escapeHtml(s.end_time || "");
    const dur = fmtDuration(s.duration_sec || 0);
    return `
      <div class="kv">
        <span>${name}</span>
        <span class="text-right font-mono">${dur}</span>
      </div>
      <div class="kv">
        <span>start</span><span class="text-right font-mono">${st || "—"}</span>
      </div>
      <div class="kv">
        <span>end</span><span class="text-right font-mono">${et || "—"}</span>
      </div>
    `;
  }).join("");
}

function startUserPolling() {
  const root = qs("#userRoot");
  if (!root) return;
  const ip = getActiveIp() || (root.dataset.ip || "").trim();
  if (!ip) return;

  const spinner = qs("#userSpinner");
  const btn = qs("#refreshUserBtn");
  let inFlight = false;

  const tick = async (refresh = false) => {
    if (inFlight) return;
    inFlight = true;
    spinner?.classList.remove("hidden");
    try {
      const data = await fetchUserData(ip, refresh);
      renderUser(data);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      spinner?.classList.add("hidden");
      inFlight = false;
    }
  };

  btn?.addEventListener("click", () => tick(true));
  window.setTimeout(() => tick(true), 250);
  window.setInterval(() => tick(false), 15000);
}

syncIpFromQuery();
wireNavIpLinks();
wireDeviceSelect();
renderActiveDeviceHighlight();
wireManualIp();
wireRemoteButtons();
wireRemoteHoldRepeat();
wireLaunchButtons();
wireAppCardLaunch();
wireChannelSearch();
wireRefreshChannels();
startLanAutoRefresh();
wireKeyboardShortcuts();
startActiveAppPolling();
gateControlsByReachability();
startUserPolling();
