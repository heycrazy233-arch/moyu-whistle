(() => {
  const labels = { working: '进行中', waiting: '等待', error: '错误', idle: '空闲' };
  const colors = { working: '#89d6b1', waiting: '#eac386', error: '#f397a2', idle: '#60a5fa' };
  const clients = {desktop: 'Codex 桌面窗口', terminal: 'Codex Terminal', vscode: 'Codex VS Code'};
  const $ = (id) => document.getElementById(id);
  let agents = [], filter = 'all', online = false, busy = false, synced = null;
  let waitingBaseline = false, previousStates = new Map();
  const state = (agent) => {
    const value = agent.event === 'done' ? 'idle' : agent.event;
    return agent.status_known === false || !Object.hasOwn(labels, value) ? null : value;
  };
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function activity(value) {
    const date = new Date(Number(value) * 1000);
    return Number(value) > 0 && Number.isFinite(date.getTime()) ? date.toLocaleString() : '无可靠活动时间';
  }
  function render() {
    const working = agents.filter(a => state(a) === 'working').length;
    const waiting = agents.filter(a => state(a) === 'waiting' && !a.collection_paused && a.collector_online !== false).length;
    document.querySelector('.whistle').dataset.waiting = String(online && waiting > 0);
    $('summary').textContent = !online ? '连接中断' : waiting ? `${waiting} 等待你处理 · ${agents.length} 会话` : `${working} 进行中 · ${agents.length} 会话`;
    $('signal').dataset.online = String(online);
    $('signal').title = $('signal').ariaLabel = online ? '本地服务已连接' : '本地服务未连接';
    $('connection').textContent = online ? '显示最近采集的任务状态；不代表实时 CPU 活动。' : '无法连接本地服务。保留上次快照，状态可能已过期。';
    const visible = agents.filter(a => filter === 'all' || (filter === 'attention' ? ['waiting', 'error'].includes(state(a)) : state(a) === filter));
    $('agents').replaceChildren();
    for (const a of visible) {
      const task = state(a), card = document.createElement('article');
      if (a.agent_key != null) card.dataset.agentKey = String(a.agent_key);
      card.style.setProperty('--state', colors[task] || '#aaa6b9');
      const collection = !online ? '服务断开 · 最后已知状态' : a.collection_paused ? '采集暂停 · 最后已知状态' : a.collector_online === false ? '采集器断开 · 最后已知状态' : a.collector_online === true ? '采集连接正常' : '未提供采集连接状态';
      const name = a.agent_type === 'codex' ? clients[a.client_type] || 'Codex' : a.agent_type || 'Agent';
      card.innerHTML = `<div class="row"><h2>${escape(a.project || '未命名项目')}</h2>${task ? `<span class="badge">● ${labels[task]}</span>` : ''}</div><p class="meta">${escape(name)} · ${escape(a.server || '未标注来源')}<br>${escape(a.session_id || '未标注会话')}</p>${a.message ? `<p class="message">${escape(a.message)}</p>` : ''}<p class="evidence ${!online || a.collection_paused || a.collector_online === false ? 'stale' : ''}">${task ? '' : '采集提示：暂无可靠任务状态<br>'}${collection}<br>活动：${escape(activity(a.last_activity))}<br>依据：${escape(a.evidence || '未提供')}</p>`;
      $('agents').append(card);
    }
    if (!visible.length) {
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = !online && !synced ? '等待本地状态服务连接。' : filter === 'all' ? '还没有采集到会话。可在控制台查看采集设置。' : '没有符合筛选条件的会话。';
      $('agents').append(empty);
    }
    $('updated').textContent = synced ? `快照同步 ${synced.toLocaleTimeString()}` : '尚未同步';
  }
  function checkWaiting() {
    // Native mode has one dedicated monitor, independent of Chromium timers.
    if (window.whistleBridge) return;
    const next = new Map(), arrivals = [], waiting = [];
    for (const a of agents) {
      if (!a.agent_key) continue;
      const key = String(a.agent_key);
      const reliable = a.status_known !== false && !a.collection_paused && a.collector_online !== false;
      const current = reliable ? state(a) : null;
      next.set(key, current);
      if (current !== 'waiting') continue;
      waiting.push(a);
      if (waitingBaseline && previousStates.get(key) !== 'waiting' && previousStates.get(key) !== null) arrivals.push(a);
    }
    previousStates = next;
    if (waitingBaseline && arrivals.length) {
      const message = `${waiting.length} 个会话正在等待你操作\n` + waiting.slice(0, 4).map(a => `${a.project || '未命名项目'} · ${a.agent_type || 'Agent'}`).join('\n');
      if (window.whistleBridge) window.whistleBridge.notifyWaiting(message);
      else { $('waiting-message').textContent = message; $('waiting-notice').hidden = false; }
    }
    if (!waiting.length) {
      $('waiting-notice').hidden = true;
      // Native notices retain pending evidence through connection failures.
    }
    waitingBaseline = true;
  }
  async function refresh() {
    if (busy) return;
    busy = true; $('refresh').disabled = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch('/api/agents', {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error('Service unavailable');
      const data = await response.json();
      if (!Array.isArray(data) || data.some(a => !a || typeof a !== 'object')) throw new Error('Invalid snapshot');
      agents = data; online = true; synced = new Date(); checkWaiting();
    } catch {
      online = false; waitingBaseline = false; previousStates.clear();
      $('waiting-notice').hidden = true;
      // Native monitor owns notice lifecycle, including disconnected snapshots.
    }
    finally { clearTimeout(timeout); busy = false; $('refresh').disabled = false; render(); }
  }
  function expand(value) {
    $('toggle').setAttribute('aria-expanded', String(value)); $('detail').hidden = !value;
    if (window.whistleBridge) window.whistleBridge.setExpanded(value);
  }
  $('toggle').onclick = () => expand($('detail').hidden);
  document.querySelector('.whistle').onclick = event => {
    if (!event.target.closest('button, a, input, select, textarea')) expand($('detail').hidden);
  };
  document.addEventListener('keydown', event => { if (event.key === 'Escape') expand(false); });
  document.querySelector('nav').onclick = event => {
    const button = event.target.closest('[data-filter]'); if (!button) return;
    filter = button.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b === button)));
    render();
  };
  $('refresh').onclick = refresh;
  window.openAgentState = (requested) => {
    filter = Object.hasOwn(labels, requested) ? requested : 'all'; expand(true);
    document.querySelectorAll('[data-filter]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === filter)));
    $('waiting-notice').hidden = true; render();
  };
  window.openWaiting = () => window.openAgentState('waiting');
  $('waiting-open').onclick = window.openWaiting;
  $('waiting-dismiss').onclick = () => { $('waiting-notice').hidden = true; };
  // Only the desktop launcher injects this bridge; browser preview has no native permissions.
  window.connectWhistle = (bridge) => {
    window.whistleBridge = bridge; $('quit').hidden = false;
    $('waiting-notice').hidden = true;
    $('quit').onclick = () => bridge.hideWindow();
    $('dashboard').onclick = event => { event.preventDefault(); bridge.openDashboard(); };
  };
  refresh(); setInterval(refresh, 2000);
})();
