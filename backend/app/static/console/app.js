/* TradeCall ops console — talks to same-origin FastAPI */

const state = {
  retailers: [],
  orders: [],
  pipeline: ["confirmed", "packed", "dispatched", "out_for_delivery", "delivered"],
  selectedRetailerId: null,
  selectedOrderId: null,
  agents: [],
  selectedAgentId: null,
  creatingAgent: false,
  calls: [],
  activeExecutionId: null,
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    let detail = data?.detail || data?.raw || res.statusText;
    if (Array.isArray(detail)) {
      detail = detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    } else if (detail && typeof detail === "object") {
      detail = JSON.stringify(detail);
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data;
}

function setHealth(ok, label) {
  const el = $("healthPill");
  el.textContent = label;
  el.classList.toggle("ok", ok);
  el.classList.toggle("bad", !ok);
}

function formatCountdown(secondsUntil) {
  if (secondsUntil == null) return "—";
  const due = secondsUntil <= 0;
  const abs = Math.abs(secondsUntil);
  const h = Math.floor(abs / 3600);
  const m = Math.floor((abs % 3600) / 60);
  const s = abs % 60;
  const core = h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
  return due ? (abs < 3600 ? `DUE ${core}` : `OVERDUE ${core}`) : core;
}

function liveSchedule(r) {
  if (!r?.schedule?.next_call_at) return null;
  const when = new Date(r.schedule.next_call_at);
  if (Number.isNaN(when.getTime())) return r.schedule;
  const seconds = Math.floor((when.getTime() - Date.now()) / 1000);
  let status = "upcoming";
  if (seconds <= 0 && seconds > -3600) status = "due";
  else if (seconds <= -3600) status = "overdue";
  return { ...r.schedule, seconds_until: seconds, status };
}

function toDatetimeLocalValue(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  // Show in local browser time for datetime-local
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderRetailers() {
  const ul = $("retailerList");
  ul.innerHTML = "";
  for (const r of state.retailers) {
    const sch = liveSchedule(r);
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "retailer" +
      (r.id === state.selectedRetailerId ? " active" : "") +
      (sch && sch.status !== "upcoming" ? " due-glow" : "");
    const timerHtml = sch
      ? `<div class="timer ${escapeHtml(sch.status)}">${escapeHtml(formatCountdown(sch.seconds_until))} · ${escapeHtml(sch.label || "")}</div>`
      : `<div class="timer">No schedule</div>`;
    btn.innerHTML = `
      <div class="shop">${escapeHtml(r.shop_name)}</div>
      <div class="meta">${escapeHtml(r.id)} · ${escapeHtml(r.phone || "—")}</div>
      <div class="last">${escapeHtml(r.last_order?.items_summary || "No orders yet")}</div>
      ${timerHtml}
    `;
    btn.addEventListener("click", () => selectRetailer(r.id));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function fillScheduleForm(r) {
  const has = !!r;
  $("btnSaveSchedule").disabled = !has;
  $("btnClearSchedule").disabled = !has || !r?.schedule;
  if (!has) {
    $("scheduleAt").value = "";
    $("scheduleNote").value = "";
    $("scheduleCadence").value = "custom";
    const cd = $("scheduleCountdown");
    cd.textContent = "—";
    cd.className = "countdown muted";
    return;
  }
  const sch = liveSchedule(r);
  $("scheduleAt").value = toDatetimeLocalValue(sch?.next_call_at) || "";
  $("scheduleNote").value = sch?.note || r.schedule?.note || "";
  $("scheduleCadence").value = sch?.cadence || r.schedule?.cadence || "custom";
  updateScheduleCountdown();
}

function updateScheduleCountdown() {
  const r = state.retailers.find((x) => x.id === state.selectedRetailerId);
  const cd = $("scheduleCountdown");
  if (!cd) return;
  const sch = liveSchedule(r);
  if (!sch) {
    cd.textContent = "No schedule";
    cd.className = "countdown muted";
    return;
  }
  cd.textContent = formatCountdown(sch.seconds_until);
  cd.className = `countdown ${sch.status}`;
  cd.title = sch.note || sch.label || "";
}

function selectRetailer(id) {
  state.selectedRetailerId = id;
  const r = state.retailers.find((x) => x.id === id);
  $("selectedLabel").textContent = r
    ? `${r.shop_name} · ${r.phone}`
    : "No retailer selected";
  $("btnCall").disabled = !r;
  renderRetailers();
  fillScheduleForm(r);
  const shopOrders = state.orders.filter((o) => o.retailer_id === id);
  if (shopOrders[0]) {
    state.selectedOrderId = shopOrders[0].order_id;
  }
  renderOrderSelect();
  renderOrderCard();
}

function presetDatetime(kind) {
  const d = new Date();
  if (kind === "30m") d.setMinutes(d.getMinutes() + 30);
  else if (kind === "2h") d.setHours(d.getHours() + 2);
  else if (kind === "tomorrow10") {
    d.setDate(d.getDate() + 1);
    d.setHours(10, 0, 0, 0);
  } else if (kind === "today17") {
    d.setHours(17, 0, 0, 0);
    if (d.getTime() < Date.now()) d.setDate(d.getDate() + 1);
  }
  $("scheduleAt").value = toDatetimeLocalValue(d.toISOString());
}

async function saveSchedule(ev) {
  ev.preventDefault();
  const id = state.selectedRetailerId;
  if (!id) return;
  const box = $("scheduleStatus");
  box.hidden = false;
  box.classList.remove("err");
  box.textContent = "Saving timeline…";
  try {
    const data = await api(`/v1/retailers/${encodeURIComponent(id)}/schedule`, {
      method: "PUT",
      body: JSON.stringify({
        next_call_at: $("scheduleAt").value,
        note: $("scheduleNote").value.trim() || null,
        cadence: $("scheduleCadence").value,
      }),
    });
    const r = state.retailers.find((x) => x.id === id);
    if (r) r.schedule = data.schedule;
    box.textContent = `Scheduled ${data.schedule?.label || ""}`;
    renderRetailers();
    fillScheduleForm(r);
  } catch (err) {
    box.classList.add("err");
    box.textContent = err.message;
  }
}

async function clearSchedule() {
  const id = state.selectedRetailerId;
  if (!id) return;
  const box = $("scheduleStatus");
  box.hidden = false;
  box.classList.remove("err");
  try {
    await api(`/v1/retailers/${encodeURIComponent(id)}/schedule`, { method: "DELETE" });
    const r = state.retailers.find((x) => x.id === id);
    if (r) r.schedule = null;
    box.textContent = "Schedule cleared";
    renderRetailers();
    fillScheduleForm(r);
  } catch (err) {
    box.classList.add("err");
    box.textContent = err.message;
  }
}

function renderOrderSelect() {
  const sel = $("orderSelect");
  const list = state.selectedRetailerId
    ? state.orders.filter((o) => o.retailer_id === state.selectedRetailerId)
    : state.orders;
  sel.innerHTML = "";
  if (!list.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No orders";
    sel.appendChild(opt);
    return;
  }
  for (const o of list) {
    const opt = document.createElement("option");
    opt.value = o.order_id;
    opt.textContent = `${o.order_id} · ${o.status}`;
    if (o.order_id === state.selectedOrderId) opt.selected = true;
    sel.appendChild(opt);
  }
  if (!state.selectedOrderId && list[0]) {
    state.selectedOrderId = list[0].order_id;
    sel.value = state.selectedOrderId;
  }
}

function currentOrder() {
  return state.orders.find((o) => o.order_id === state.selectedOrderId) || null;
}

function renderOrderCard() {
  const card = $("orderCard");
  const o = currentOrder();
  if (!o) {
    card.className = "order-card empty";
    card.innerHTML = `<p class="muted">Pick an order to inspect.</p>`;
    renderPipeline(null);
    return;
  }
  card.className = "order-card";
  const items = (o.items || [])
    .map((i) => `<li>${escapeHtml(String(i.qty))} ${escapeHtml(i.unit || "")} ${escapeHtml(i.name || i.sku || "")}</li>`)
    .join("");
  card.innerHTML = `
    <h3>${escapeHtml(o.order_id)}</h3>
    <div class="status-line">
      <span class="badge">${escapeHtml(o.status)}</span>
      <span> · ${escapeHtml(o.eta_text || "ETA TBD")}</span>
    </div>
    <ul>${items || "<li>No line items</li>"}</ul>
  `;
  renderPipeline(o.status);
}

function renderPipeline(current) {
  const wrap = $("statusPipeline");
  wrap.innerHTML = "";
  for (const s of state.pipeline) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn small" + (s === current ? " active" : "");
    btn.textContent = s;
    btn.disabled = !state.selectedOrderId;
    btn.addEventListener("click", () => scrubStatus(s));
    wrap.appendChild(btn);
  }
}

async function scrubStatus(status) {
  if (!state.selectedOrderId) return;
  try {
    await api(`/v1/orders/${encodeURIComponent(state.selectedOrderId)}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    await loadOrders();
    renderOrderSelect();
    renderOrderCard();
  } catch (err) {
    alert(`Status update failed: ${err.message}`);
  }
}

function renderWa(messages) {
  const ul = $("waList");
  ul.innerHTML = "";
  if (!messages?.length) {
    ul.innerHTML = `<li class="muted">Outbox empty</li>`;
    return;
  }
  for (const m of messages) {
    const li = document.createElement("li");
    li.className = "wa-item";
    li.innerHTML = `
      <div class="to">→ ${escapeHtml(m.to || "")} · ${escapeHtml(m.status || "")}</div>
      <p class="body">${escapeHtml(m.summary_text || "")}</p>
      <div class="oid">${escapeHtml(m.order_id || "")}</div>
    `;
    ul.appendChild(li);
  }
}

function renderCallbacks(rows) {
  const ul = $("cbList");
  if (!ul) return;
  ul.innerHTML = "";
  if (!rows?.length) {
    ul.innerHTML = `<li class="muted">No callbacks yet</li>`;
    return;
  }
  for (const c of rows) {
    const li = document.createElement("li");
    li.className = "wa-item";
    li.innerHTML = `
      <div class="to">${escapeHtml(c.id || "")} · ${escapeHtml(c.disposition || "callback")}</div>
      <p class="body">${escapeHtml(c.shop_name || c.phone || "—")} → <strong>${escapeHtml(c.callback_slot || "")}</strong></p>
      <div class="oid">${escapeHtml(c.reason || "")}</div>
    `;
    ul.appendChild(li);
  }
}

function renderAgents() {
  const ul = $("agentList");
  if (!ul) return;
  ul.innerHTML = "";
  if (!state.agents.length) {
    ul.innerHTML = `<li class="muted">No agents in registry</li>`;
    return;
  }
  for (const a of state.agents) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "agent-card" + (a.agent_id === state.selectedAgentId && !state.creatingAgent ? " active" : "");
    const err = a.error ? ` · err` : "";
    btn.innerHTML = `
      <div class="name">${escapeHtml(a.agent_name || a.name || "Agent")}</div>
      <div class="meta">${escapeHtml(a.role || "?")}${err} · ${escapeHtml((a.agent_id || "").slice(0, 8))}…</div>
      <div class="meta">${escapeHtml(a.label || a.agent_status || "")}</div>
    `;
    btn.addEventListener("click", () => selectAgent(a.agent_id));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function selectAgent(id) {
  state.creatingAgent = false;
  state.selectedAgentId = id;
  const a = state.agents.find((x) => x.agent_id === id);
  $("agentFormTitle").textContent = "Customize agent";
  $("agentEditId").value = id || "";
  $("agentName").value = a?.agent_name || a?.name || "";
  $("agentRole").value = a?.role || "outbound";
  $("agentRole").disabled = true;
  $("agentWelcome").value = a?.agent_welcome_message || "";
  $("agentSystem").value = a?.system_prompt || "";
  $("agentDefault").checked = false;
  $("agentDefault").closest("label").hidden = true;
  $("btnCancelAgent").hidden = true;
  $("btnSaveAgent").textContent = "Save changes";
  renderAgents();
}

function startCreateAgent() {
  state.creatingAgent = true;
  state.selectedAgentId = null;
  $("agentFormTitle").textContent = "Make new agent";
  $("agentEditId").value = "";
  $("agentName").value = "";
  $("agentRole").value = "outbound";
  $("agentRole").disabled = false;
  $("agentWelcome").value = "नमस्ते {{shop_name}}, मैं रवि बोल रहा हूँ भारत हार्डवेयर डिस्ट्रीब्यूटर्स से।";
  $("agentSystem").value =
    "You are Ravi from Bharat Hardware Distributors — warm and human. Follow graph nodes. Keep replies short.";
  $("agentDefault").checked = false;
  $("agentDefault").closest("label").hidden = false;
  $("btnCancelAgent").hidden = false;
  $("btnSaveAgent").textContent = "Create agent";
  renderAgents();
}

async function loadAgents() {
  try {
    const data = await api("/v1/agents");
    state.agents = data.agents || [];
    if (!state.creatingAgent) {
      if (
        state.selectedAgentId &&
        state.agents.some((a) => a.agent_id === state.selectedAgentId)
      ) {
        selectAgent(state.selectedAgentId);
      } else if (state.agents[0]?.agent_id) {
        selectAgent(state.agents[0].agent_id);
      } else {
        renderAgents();
      }
    } else {
      renderAgents();
    }
  } catch (err) {
    const ul = $("agentList");
    if (ul) ul.innerHTML = `<li class="muted">${escapeHtml(err.message)}</li>`;
  }
}

async function saveAgent(ev) {
  ev.preventDefault();
  const box = $("agentFormStatus");
  box.hidden = false;
  box.classList.remove("err");
  const name = $("agentName").value.trim();
  const welcome = $("agentWelcome").value.trim();
  const system = $("agentSystem").value.trim();
  try {
    if (state.creatingAgent) {
      box.textContent = "Creating agent on Bolna…";
      const data = await api("/v1/agents", {
        method: "POST",
        body: JSON.stringify({
          role: $("agentRole").value,
          agent_name: name,
          agent_welcome_message: welcome,
          system_prompt: system || null,
          set_as_default: $("agentDefault").checked,
        }),
      });
      box.textContent = `Created ${data.agent_id}`;
      state.creatingAgent = false;
      state.selectedAgentId = data.agent_id;
      await loadAgents();
    } else {
      const id = $("agentEditId").value;
      if (!id) throw new Error("No agent selected");
      box.textContent = "Saving customization…";
      await api(`/v1/agents/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({
          agent_name: name,
          agent_welcome_message: welcome,
          system_prompt: system || null,
        }),
      });
      box.textContent = "Saved";
      await loadAgents();
    }
  } catch (err) {
    box.classList.add("err");
    box.textContent = err.message;
  }
}

async function loadAll() {
  const [health, retailers, orders, wa, cbs, calls] = await Promise.all([
    api("/health"),
    api("/v1/retailers"),
    api("/v1/orders?limit=50"),
    api("/v1/whatsapp/outbox"),
    api("/v1/callbacks"),
    api("/v1/calls/recent?limit=15"),
  ]);
  setHealth(health.status === "ok", `${health.service} · ${health.phase}`);
  state.retailers = retailers.retailers || [];
  state.orders = orders.orders || [];
  state.pipeline = orders.status_pipeline || state.pipeline;
  if (!state.selectedRetailerId && state.retailers[0]) {
    state.selectedRetailerId = state.retailers[0].id;
  }
  renderRetailers();
  const r = state.retailers.find((x) => x.id === state.selectedRetailerId);
  $("selectedLabel").textContent = r ? `${r.shop_name} · ${r.phone}` : "No retailer selected";
  $("btnCall").disabled = !r;
  fillScheduleForm(r);
  renderOrderSelect();
  renderOrderCard();
  renderWa(wa.messages || []);
  renderCallbacks(cbs.callbacks || []);
  renderCalls(calls.calls || []);
  if (!$("agentsPanel").hidden) {
    loadAgents().catch(() => {});
  }
}

async function loadOrders() {
  const orders = await api("/v1/orders?limit=50");
  state.orders = orders.orders || [];
  state.pipeline = orders.status_pipeline || state.pipeline;
}

function renderCalls(rows) {
  const ul = $("callList");
  if (!ul) return;
  state.calls = rows || state.calls || [];
  ul.innerHTML = "";
  if (!state.calls.length) {
    ul.innerHTML = `<li class="muted">No outbound calls yet</li>`;
    return;
  }
  for (const c of state.calls) {
    const li = document.createElement("li");
    li.className = "wa-item";
    const orderLine = c.order_id
      ? `<strong>${escapeHtml(c.order_id)}</strong> · ${escapeHtml(c.items_summary || "order booked")}`
      : c.status === "in_progress"
        ? `<em>In progress — waiting for order…</em>`
        : c.status === "no_order"
          ? `<em>Ended — no new order (earlier ORD still on file)</em>`
          : `<em>No order on this call</em>`;
    li.innerHTML = `
      <div class="to">${escapeHtml(c.shop_name || c.retailer_id || "")} · ${escapeHtml(c.status || "")}</div>
      <p class="body">${orderLine}</p>
      <div class="oid">${escapeHtml((c.execution_id || "").slice(0, 8))}…</div>
    `;
    if (c.order_id) {
      li.style.cursor = "pointer";
      li.addEventListener("click", () => {
        if (c.retailer_id) selectRetailer(c.retailer_id);
        state.selectedOrderId = c.order_id;
        renderOrderSelect();
        renderOrderCard();
        const card = $("orderCard");
        card.classList.add("highlight");
        setTimeout(() => card.classList.remove("highlight"), 2500);
      });
    }
    ul.appendChild(li);
  }
}

function showCallResult(call) {
  const card = $("callResultCard");
  if (!card || !call?.order_id) return;
  card.hidden = false;
  card.classList.add("flash");
  $("callResultOrder").textContent = call.order_id;
  $("callResultMeta").textContent = [
    call.shop_name || call.retailer_id || "",
    call.items_summary || "",
    "confirmed",
  ]
    .filter(Boolean)
    .join(" · ");
  setTimeout(() => card.classList.remove("flash"), 2000);
}

function stopCallPoll() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  state.activeExecutionId = null;
}

async function pollCallUntilOrder(executionId, retailerId) {
  stopCallPoll();
  state.activeExecutionId = executionId;
  const box = $("callStatus");
  let tries = 0;
  const maxTries = 80; // ~4 min at 3s
  state.pollTimer = setInterval(async () => {
    tries += 1;
    try {
      const data = await api(`/v1/calls/${encodeURIComponent(executionId)}`);
      const call = data.call || {};
      if (call.order_id) {
        stopCallPoll();
        box.classList.remove("err");
        box.classList.add("ok-order");
        box.textContent = `Order booked: ${call.order_id} · ${call.items_summary || ""}`;
        showCallResult(call);
        await loadOrders();
        if (retailerId) {
          state.selectedRetailerId = retailerId;
          state.selectedOrderId = call.order_id;
          renderRetailers();
          fillScheduleForm(state.retailers.find((x) => x.id === retailerId));
        }
        renderOrderSelect();
        renderOrderCard();
        $("orderCard")?.classList.add("highlight");
        const [recent, wa] = await Promise.all([
          api("/v1/calls/recent?limit=15"),
          api("/v1/whatsapp/outbox"),
        ]);
        renderCalls(recent.calls || []);
        renderWa(wa.messages || []);
        return;
      }
      box.classList.remove("ok-order");
      box.textContent = `Call in progress… waiting for order (${tries * 3}s) · ${executionId.slice(0, 8)}…`;
      const [recent, wa] = await Promise.all([
        api("/v1/calls/recent?limit=15"),
        api("/v1/whatsapp/outbox"),
      ]);
      renderCalls(recent.calls || []);
      renderWa(wa.messages || []);
    } catch {
      /* keep polling */
    }
    if (tries >= maxTries) {
      stopCallPoll();
      box.textContent = "Call watch timed out — refresh to see if an order appeared.";
    }
  }, 3000);
}

async function placeCall() {
  const id = state.selectedRetailerId;
  if (!id) return;
  const box = $("callStatus");
  box.hidden = false;
  box.classList.remove("err", "ok-order");
  box.textContent = "Queuing outbound call via Bolna…";
  $("btnCall").disabled = true;
  stopCallPoll();
  try {
    const data = await api("/v1/calls/outbound", {
      method: "POST",
      body: JSON.stringify({ retailer_id: id }),
    });
    const eid = data.execution_id;
    box.textContent = eid
      ? `Calling ${data.shop_name}… watching for order · ${eid.slice(0, 8)}…`
      : `Queued ${data.shop_name} → ${data.dialed}`;
    if (eid) pollCallUntilOrder(eid, id);
    const recent = await api("/v1/calls/recent?limit=15");
    renderCalls(recent.calls || []);
  } catch (err) {
    box.classList.add("err");
    box.textContent = err.message;
  } finally {
    $("btnCall").disabled = !state.selectedRetailerId;
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function tickClock() {
  $("clock").textContent = new Date().toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

$("btnRefresh").addEventListener("click", () => {
  loadAll().catch((e) => setHealth(false, e.message));
});
$("btnCall").addEventListener("click", placeCall);
$("orderSelect").addEventListener("change", (e) => {
  state.selectedOrderId = e.target.value || null;
  renderOrderCard();
});
$("btnAgents").addEventListener("click", () => {
  const panel = $("agentsPanel");
  panel.hidden = !panel.hidden;
  if (!panel.hidden) loadAgents().catch((e) => alert(e.message));
});
$("btnNewAgent").addEventListener("click", startCreateAgent);
$("btnCancelAgent").addEventListener("click", () => {
  state.creatingAgent = false;
  if (state.agents[0]) selectAgent(state.agents[0].agent_id);
});
$("agentForm").addEventListener("submit", saveAgent);
$("scheduleForm").addEventListener("submit", saveSchedule);
$("btnClearSchedule").addEventListener("click", clearSchedule);
document.querySelectorAll("[data-preset]").forEach((btn) => {
  btn.addEventListener("click", () => presetDatetime(btn.getAttribute("data-preset")));
});

function tickTimers() {
  // Update countdown labels in place (avoid rebuilding the list every second)
  document.querySelectorAll("#retailerList .retailer").forEach((btn, idx) => {
    const r = state.retailers[idx];
    if (!r) return;
    const sch = liveSchedule(r);
    const timer = btn.querySelector(".timer");
    if (!timer) return;
    if (!sch) {
      timer.textContent = "No schedule";
      timer.className = "timer";
      btn.classList.remove("due-glow");
      return;
    }
    timer.textContent = `${formatCountdown(sch.seconds_until)} · ${sch.label || ""}`;
    timer.className = `timer ${sch.status}`;
    btn.classList.toggle("due-glow", sch.status !== "upcoming");
  });
  updateScheduleCountdown();
}

tickClock();
setInterval(tickClock, 1000);
setInterval(tickTimers, 1000);
loadAll().catch((e) => setHealth(false, e.message));
setInterval(() => {
  loadAll().catch(() => {});
}, 12000);
