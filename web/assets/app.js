const STATUS = ["working", "waiting", "error", "done", "idle"];
const LABELS = { idle: "Idle", working: "Working", waiting: "Waiting", error: "Error", done: "Done" };

let agents = [];
let activeFilter = "all";

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
  agents.forEach((agent) => { counts[agent.event] = (counts[agent.event] || 0) + 1; });
  metrics.innerHTML = STATUS.map((status) => `
    <div class="metric" style="--status: var(--${status})">
      <span class="metric-count">${counts[status]}</span>
      <span class="metric-label">${LABELS[status]}</span>
    </div>`).join("");
}

function renderAgents() {
  const visibleAgents = activeFilter === "all" ? agents : agents.filter((agent) => agent.event === activeFilter);
  if (!visibleAgents.length) {
    const emptyState = document.querySelector("#empty-state").content.cloneNode(true);
    if (activeFilter !== "all") {
      emptyState.querySelector("h3").textContent = "No matching agents";
      emptyState.querySelector("p").textContent = `No agents are currently ${LABELS[activeFilter].toLowerCase()}.`;
    }
    list.replaceChildren(emptyState);
    return;
  }
  list.innerHTML = visibleAgents.map((agent) => {
    const status = STATUS.includes(agent.event) ? agent.event : "idle";
    return `
      <article class="agent-card" style="--status: var(--${status})">
        <div class="agent-main">
          <span class="status-dot" aria-hidden="true"></span>
          <div class="agent-copy">
            <p class="agent-name">${escapeHtml(agent.project)} <span aria-hidden="true">/</span> ${escapeHtml(agent.session_id)}</p>
            <p class="agent-message">${escapeHtml(agent.message || "No activity message")}</p>
          </div>
        </div>
        <div class="agent-meta">
          <span>${escapeHtml(agent.server)}</span>
          <span>${escapeHtml(agent.agent_type)}</span>
          <span>${escapeHtml(agent.tmux_session || "no tmux")}</span>
        </div>
        <span class="status">${LABELS[status]}</span>
      </article>`;
  }).join("");
}

function setConnection(state, label) {
  connection.className = `connection ${state}`;
  connection.lastElementChild.textContent = label;
}

async function refresh() {
  refreshButton.classList.add("is-loading");
  try {
    const response = await fetch("/api/agents", { cache: "no-store" });
    if (!response.ok) throw new Error("Status service unavailable");
    agents = await response.json();
    setConnection("is-live", "Live local service");
    updatedAt.textContent = `${agents.length} tracked agent${agents.length === 1 ? "" : "s"} · refreshed ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    agents = [];
    setConnection("is-offline", "Service unavailable");
    updatedAt.textContent = "Unable to reach the local status service.";
  } finally {
    renderMetrics();
    renderAgents();
    refreshButton.classList.remove("is-loading");
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
