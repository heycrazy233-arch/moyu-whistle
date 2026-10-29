// Isolated presentation checks. No writes to the running service or database.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.dataset = {}; this.hidden = false; this.attributes = {}; this.style = {setProperty() {}}; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  setAttribute(key, value) { this.attributes[key] = value; }
}
const elements = new Map();
const get = key => { if (!elements.has(key)) elements.set(key, new Element()); return elements.get(key); };
get('detail').hidden = true;
let response = [], fail = false;
const sandbox = {
  document: {getElementById:get, createElement:() => new Element(), querySelector:get, querySelectorAll:() => [], addEventListener() {}},
  window: {}, AbortController, Date, setTimeout, clearTimeout, setInterval() {},
  fetch: async () => { if (fail) throw new Error('Disconnected'); return {ok:true, json:async () => response}; },
};
vm.runInNewContext(fs.readFileSync('web/assets/whistle.js', 'utf8'), sandbox);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  await settle();
  assert.match(get('agents').children[0].textContent, /还没有/);
  response = [
    {agent_key:'a', project:'<script>alert(1)</script>', event:'working', collection_paused:true, last_activity:1700000000},
    {agent_key:'b', event:'idle', status_known:false},
    {agent_key:'c', event:'unrecognized'},
    {agent_key:'d', event:'waiting'},
    {agent_key:'e', event:'error'},
    {agent_key:'f', event:'idle', agent_type:'codex', client_type:'desktop'},
    {agent_key:'g', event:'done', agent_type:'codex', client_type:'terminal'},
  ];
  await get('refresh').onclick();
  const cards = get('agents').children;
  assert.equal(cards[0].dataset.agentKey, 'a');
  assert.match(cards[0].innerHTML, /进行中/);
  assert.match(cards[0].innerHTML, /采集暂停/);
  assert.match(cards[0].innerHTML, /&lt;script&gt;/);
  assert.doesNotMatch(cards[0].innerHTML, /<script>/);
  assert.match(cards[1].innerHTML, /暂无可靠任务状态/);
  assert.match(cards[2].innerHTML, /暂无可靠任务状态/);
  assert.doesNotMatch(cards[1].innerHTML, /class="badge"/);
  assert.match(cards[3].innerHTML, /等待/);
  assert.match(cards[4].innerHTML, /错误/);
  assert.match(cards[5].innerHTML, /空闲/);
  assert.match(cards[5].innerHTML, /Codex 桌面窗口/);
  assert.match(cards[6].innerHTML, /空闲/);
  assert.match(cards[6].innerHTML, /Codex Terminal/);
  for (const filter of ['working', 'waiting', 'error', 'idle']) {
    get('nav').onclick({target:{closest:() => ({dataset:{filter}})}});
    assert.equal(get('agents').children.length, filter === 'idle' ? 2 : 1);
  }
  get('nav').onclick({target:{closest:() => ({dataset:{filter:'all'}})}});
  fail = true;
  await get('refresh').onclick();
  assert.equal(get('agents').children.length, 7);
  assert.match(get('agents').children[0].innerHTML, /服务断开/);
  assert.match(get('agents').children[0].innerHTML, /进行中/);
  fail = false;
  await get('refresh').onclick();
  assert.equal(get('signal').dataset.online, 'true');
  get('toggle').onclick();
  assert.equal(get('detail').hidden, false);
  get('toggle').onclick();
  assert.equal(get('detail').hidden, true);
  let alerts = 0;
  let hiddenNotice = true;
  Object.defineProperty(get('waiting-notice'), 'hidden', {get() {return hiddenNotice;}, set(value) {hiddenNotice = value; if (!value) alerts++;}});
  response = [{agent_key:'notify', event:'working'}];
  await get('refresh').onclick();
  response[0].event = 'waiting';
  await get('refresh').onclick();
  assert.equal(alerts, 1);
  await get('refresh').onclick();
  assert.equal(alerts, 1, 'Persistent waiting must not repeat');
  response[0].event = 'working'; await get('refresh').onclick();
  response[0].event = 'waiting'; await get('refresh').onclick();
  assert.equal(alerts, 2, 'A new waiting transition must notify');
  fail = true; await get('refresh').onclick();
  fail = false; await get('refresh').onclick();
  assert.equal(alerts, 2, 'Reconnect establishes a baseline');
  response[0].collection_paused = true; await get('refresh').onclick();
  response[0].collection_paused = false; await get('refresh').onclick();
  assert.equal(alerts, 2, 'Resume must not generate stale alerts');
  response = [{agent_key:'new', event:'waiting', status_known:false}];
  await get('refresh').onclick();
  assert.equal(alerts, 2, 'Unknown must not notify');
  sandbox.window.whistleBridge = {notifyWaiting() {throw Error('Native duplicate notification');}, clearWaiting() {throw Error('Webpage must not clear native notice');}};
  response = [{agent_key:'native', event:'waiting'}];
  await get('refresh').onclick();
  fail = true; await get('refresh').onclick();
  console.log('PASS: four states/filters, escaping, unknown, pause, reconnect, expand/collapse, Waiting transition deduplication');
})().catch(error => { console.error(error); process.exitCode = 1; });
