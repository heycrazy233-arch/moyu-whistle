const settingsForm = document.querySelector('#settings-form');
const serverRows = document.querySelector('#ssh-servers');
const settingsResult = document.querySelector('#settings-result');
let loadedSettings = false;

function addServer(profile = {name: '', host: '', port: 22, script: 'moyu-whistle-collector.py', enabled: false}) {
  if (serverRows.children.length >= 8) return;
  const row = document.createElement('fieldset');
  row.className = 'ssh-row';
  const legend = document.createElement('legend');
  legend.textContent = 'SSH 连接';
  row.append(legend);
  for (const [name, title, type] of [['enabled', '启用', 'checkbox'], ['name', '机器别名（唯一）', 'text'], ['host', 'SSH 地址 / 配置别名', 'text'], ['port', 'SSH 端口', 'number'], ['script', '远端采集脚本路径', 'text']]) {
    const label = document.createElement('label');
    label.append(document.createTextNode(title));
    const input = document.createElement('input');
    input.name = name;
    input.type = type;
    if (type === 'checkbox') input.checked = profile[name];
    else { input.value = profile[name]; input.required = true; }
    if (name === 'port') { input.min = 1; input.max = 65535; }
    label.append(input);
    row.append(label);
  }
  const remove = document.createElement('button');
  remove.type = 'button'; remove.textContent = '×'; remove.title = '移除服务器配置';
  remove.setAttribute('aria-label', '移除服务器配置');
  remove.onclick = () => row.remove();
  row.append(remove);
  serverRows.append(row);
}

function showMonitor(monitor) {
  const target = document.querySelector('#monitor-status');
  target.replaceChildren();
  const heading = document.createElement('p');
  heading.textContent = `${monitor.running === false ? '采集器未启动（需 --collect）' : monitor.active ? '采集时段内' : '自动采集已暂停'} · ${monitor.timezone || '本机时区'}`;
  target.append(heading);
  for (const [name, source] of Object.entries(monitor.sources)) {
    const line = document.createElement('p');
    line.textContent = `${name} · ${source.state}${source.duration_ms !== undefined ? ` · 最近采集耗时 ${source.duration_ms} ms · ${source.count} 个会话` : ''}${source.error ? ` · ${source.error}` : ''}`;
    target.append(line);
  }
}

async function loadSettings() {
  try {
    const response = await fetch('/api/settings', {cache: 'no-store', signal: AbortSignal.timeout(8000)});
    if (!response.ok) throw new Error('无法读取设置');
    const data = await response.json();
    if (!loadedSettings) {
      for (const key of ['enabled', 'scheduled']) document.querySelector(`#monitor-${key}`).checked = data.settings[key];
      document.querySelector('#monitor-logs').checked = data.settings.allow_logs;
      for (const key of ['interval', 'start', 'end']) document.querySelector(`#monitor-${key}`).value = data.settings[key];
      serverRows.replaceChildren(); data.settings.servers.forEach(addServer);
      loadedSettings = true;
    }
    showMonitor(data.monitor);
  } catch (error) { settingsResult.textContent = '无法读取设置，请确认本地服务在线。'; }
}

document.querySelector('#add-server').onclick = () => addServer();
settingsForm.onsubmit = async (event) => {
  event.preventDefault();
  const value = {servers: []};
  for (const key of ['enabled', 'scheduled']) value[key] = document.querySelector(`#monitor-${key}`).checked;
  value.allow_logs = document.querySelector('#monitor-logs').checked;
  value.interval = Number(document.querySelector('#monitor-interval').value);
  for (const key of ['start', 'end']) value[key] = document.querySelector(`#monitor-${key}`).value;
  for (const row of serverRows.children) {
    const profile = {};
    for (const input of row.querySelectorAll('input')) profile[input.name] = input.type === 'checkbox' ? input.checked : input.name === 'port' ? Number(input.value) : input.value.trim();
    value.servers.push(profile);
  }
  try {
    const response = await fetch('/api/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value), signal: AbortSignal.timeout(8000)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || result.detail || '保存失败');
    settingsResult.textContent = '已保存，下一个采集周期生效。';
    showMonitor(result.monitor);
  } catch (error) { settingsResult.textContent = String(error.message); }
};
loadSettings();
setInterval(() => { if (document.querySelector('#settings-panel').open) loadSettings(); }, 5000);
