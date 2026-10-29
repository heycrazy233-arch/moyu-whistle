const STATUS = ["working", "waiting", "error", "idle"];
const LABELS = { idle: "Idle", working: "Working", waiting: "Waiting", error: "Error", done: "Done", unknown: "Unknown", offline: "Offline", paused: "Paused" };
const CODEX_CLIENTS = { desktop: "Codex 桌面窗口", terminal: "Codex Terminal", vscode: "Codex VS Code" };

function agentLabel(agent) {
  return agent.agent_type === "codex" ? (CODEX_CLIENTS[agent.client_type] || "Codex") : agent.agent_type;
}

let agents = [];
let activeFilter = "all";
let refreshing = false;

function displayStatus(agent) {
  if (agent.status_known === false) return null;
  const state = agent.event === "done" ? "idle" : agent.event;
  return STATUS.includes(state) ? state : null;
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
  const markup = visibleAgents.map((agent) => {
    const observed = displayStatus(agent);
    const status = observed || "unknown";
    const activity = agent.last_activity ? new Date(agent.last_activity * 1000).toLocaleString() : "No activity recorded";
    return `
      <article class="agent-card" style="--status: var(--${status})">
        <div class="agent-main">
          <span class="status-dot" aria-hidden="true"></span>
          <div class="agent-copy">
            <p class="agent-name">${escapeHtml(agent.project)} <span aria-hidden="true">/</span> <span>${escapeHtml(String(agent.session_id || '').length > 16 ? `${String(agent.session_id).slice(0, 8)}…${String(agent.session_id).slice(-4)}` : agent.session_id)}</span></p>
            <p class="agent-message">${escapeHtml(agent.message || "No activity message")}</p>
            <p class="agent-message">${escapeHtml(agent.evidence || "event")} · ${escapeHtml(agent.presence || "reported")} · ${escapeHtml(activity)}</p>
          </div>
        </div>
        <div class="agent-meta">
          <span>${escapeHtml(agent.server)}</span>
          <span>${escapeHtml(agentLabel(agent))}</span>
          <span>${escapeHtml(agent.tmux_session || "no tmux")}</span>
        </div>
        ${observed ? `<span class="status">${LABELS[observed]}</span>` : ''}
      </article>`;
  }).join("");
  if (list.innerHTML !== markup) list.innerHTML = markup;
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
    const uncertain = agents.filter(agent => !displayStatus(agent)).length;
    const stale = agents.some(agent => agent.collection_paused || agent.collector_online === false);
    setConnection(stale || uncertain ? "is-offline" : "is-live",
      `${stale ? '采集暂停或断开，显示最后已知状态' : 'Live local service'}${uncertain ? ` · ${uncertain} 个会话暂无法确认状态` : ''}`);
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
