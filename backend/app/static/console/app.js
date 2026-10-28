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

function renderRetailers() {
  const ul = $("retailerList");
  ul.innerHTML = "";
  for (const r of state.retailers) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "retailer" + (r.id === state.selectedRetailerId ? " active" : "");
    btn.innerHTML = `
      <div class="shop">${escapeHtml(r.shop_name)}</div>
      <div class="meta">${escapeHtml(r.id)} · ${escapeHtml(r.phone || "—")}</div>
      <div class="last">${escapeHtml(r.last_order?.items_summary || "No orders yet")}</div>
    `;
    btn.addEventListener("click", () => selectRetailer(r.id));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function selectRetailer(id) {
  state.selectedRetailerId = id;
  const r = state.retailers.find((x) => x.id === id);
  $("selectedLabel").textContent = r
    ? `${r.shop_name} · ${r.phone}`
    : "No retailer selected";
  $("btnCall").disabled = !r;
  renderRetailers();
  const shopOrders = state.orders.filter((o) => o.retailer_id === id);
  if (shopOrders[0]) {
    state.selectedOrderId = shopOrders[0].order_id;
  }
  renderOrderSelect();
  renderOrderCard();
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
  const [health, retailers, orders, wa, cbs] = await Promise.all([
    api("/health"),
    api("/v1/retailers"),
    api("/v1/orders?limit=50"),
    api("/v1/whatsapp/outbox"),
    api("/v1/callbacks"),
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
  renderOrderSelect();
  renderOrderCard();
  renderWa(wa.messages || []);
  renderCallbacks(cbs.callbacks || []);
  if (!$("agentsPanel").hidden) {
    loadAgents().catch(() => {});
  }
}

async function loadOrders() {
  const orders = await api("/v1/orders?limit=50");
  state.orders = orders.orders || [];
  state.pipeline = orders.status_pipeline || state.pipeline;
}

async function placeCall() {
  const id = state.selectedRetailerId;
  if (!id) return;
  const box = $("callStatus");
  box.hidden = false;
  box.classList.remove("err");
  box.textContent = "Queuing outbound call via Bolna…";
  $("btnCall").disabled = true;
  try {
    const data = await api("/v1/calls/outbound", {
      method: "POST",
      body: JSON.stringify({ retailer_id: id }),
    });
    box.textContent = `Queued ${data.shop_name} → ${data.dialed} · execution ${data.execution_id || "?"}`;
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

tickClock();
setInterval(tickClock, 1000);
loadAll().catch((e) => setHealth(false, e.message));
setInterval(() => {
  loadAll().catch(() => {});
}, 12000);
