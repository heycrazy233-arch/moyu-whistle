const STATUS = ["working", "waiting", "error", "done", "idle", "unknown", "offline", "paused"];
const LABELS = { idle: "Idle", working: "Working", waiting: "Waiting", error: "Error", done: "Done", unknown: "Unknown", offline: "Offline", paused: "Paused" };

let agents = [];
let activeFilter = "all";
let refreshing = false;

function displayStatus(agent) {
  if (agent.collection_paused) return "paused";
  if (agent.collector_online === false) return "offline";
  if (agent.status_known === false) return "unknown";
  return agent.event;
}

const list = document.querySelector("#agent-list");
const metrics = document.querySelector("#metrics");
const updatedAt = document.querySelector("#updated-at");
const connection = document.querySelector("#connection");
const refreshButton = document.querySelector("#refresh");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

function renderMetrics() {
  const counts = Object.fromEntries(STATUS.map((status) => [status, 0]));
  agents.forEach((agent) => { const state = displayStatus(agent); counts[state] = (counts[state] || 0) + 1; });
  metrics.innerHTML = STATUS.map((status) => `
    <div class="metric" style="--status: var(--${status})">
      <span class="metric-count">${counts[status]}</span>
      <span class="metric-label">${LABELS[status]}</span>
    </div>`).join("");
}

function renderAgents() {
  const visibleAgents = activeFilter === "all" ? agents : agents.filter((agent) => displayStatus(agent) === activeFilter);
  if (!visibleAgents.length) {
    const emptyState = document.querySelector("#empty-state").content.cloneNode(true);
    if (activeFilter !== "all") {
      emptyState.querySelector("h3").textContent = "No matching agents";
      emptyState.querySelector("p").textContent = `No agents are currently ${(LABELS[activeFilter] || activeFilter).toLowerCase()}.`;
    }
    list.replaceChildren(emptyState);
    return;
  }
  list.innerHTML = visibleAgents.map((agent) => {
    const observed = displayStatus(agent);
    const status = STATUS.includes(observed) ? observed : "idle";
    const activity = agent.last_activity ? new Date(agent.last_activity * 1000).toLocaleString() : "No activity recorded";
    return `
      <article class="agent-card" style="--status: var(--${status})">
        <div class="agent-main">
          <span class="status-dot" aria-hidden="true"></span>
          <div class="agent-copy">
            <p class="agent-name">${escapeHtml(agent.project)} <span aria-hidden="true">/</span> ${escapeHtml(agent.session_id)}</p>
            <p class="agent-message">${escapeHtml(agent.message || "No activity message")}</p>
            <p class="agent-message">${escapeHtml(agent.evidence || "event")} · ${escapeHtml(agent.presence || "reported")} · ${escapeHtml(activity)}</p>
          </div>
        </div>
        <div class="agent-meta">
          <span>${escapeHtml(agent.server)}</span>
          <span>${escapeHtml(agent.agent_type)}</span>
          <span>${escapeHtml(agent.tmux_session || "no tmux")}</span>
        </div>
        <span class="status">${observed === "paused" ? "Paused" : observed === "offline" ? "Offline" : observed === "unknown" ? "Unknown" : LABELS[status]}</span>
      </article>`;
  }).join("");
}

function setConnection(state, label) {
  connection.className = `connection ${state}`;
  connection.lastElementChild.textContent = label;
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  refreshButton.classList.add("is-loading");
  try {
    const response = await fetch("/api/agents", { cache: "no-store", signal: AbortSignal.timeout(8000) });
    if (!response.ok) throw new Error("Status service unavailable");
    agents = await response.json();
    setConnection("is-live", "Live local service");
    updatedAt.textContent = `${agents.length} tracked agent${agents.length === 1 ? "" : "s"} · refreshed ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    agents = agents.map((agent) => ({...agent, collector_online: false}));
    setConnection("is-offline", "Service unavailable");
    updatedAt.textContent = "Unable to reach the local status service.";
  } finally {
    renderMetrics();
    renderAgents();
    refreshButton.classList.remove("is-loading");
    refreshing = false;
  }
}

document.querySelector("#filters").addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (!button) return;
  activeFilter = button.dataset.filter;
  document.querySelectorAll("[data-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
  renderAgents();
});

refreshButton.addEventListener("click", refresh);
refresh();
window.setInterval(refresh, 2000);
