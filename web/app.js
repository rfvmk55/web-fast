/* web-fast 前端 · 多标签终端 */
const $ = s => document.querySelector(s);
const cmdEl = () => $('#cmd');

const state = {
  tools: [],
  appRoot: '',
  tabs: [],
  active: 0,
  seqTab: 0,
  seqReq: 0,
  candCache: {},
  version: '',
};

function CT() { return state.tabs[state.active] || null; }

const ANSI_COLOR = {
  30: '#6e7681', 31: '#ff7b72', 32: '#3fb950', 33: '#d29922', 34: '#58a6ff',
  35: '#bc8cff', 36: '#39c5cf', 37: '#b1bac4',
  90: '#6e7681', 91: '#ffa198', 92: '#56d364', 93: '#e3b341', 94: '#79c0ff',
  95: '#d2a8ff', 96: '#56d4dd', 97: '#f0f6fc'
};

/* 管道下大多数工具不输出 ANSI，按内容给它上色 */
const C_TIME = '#39c5cf';
const C_PATH = '#79c0ff';
const C_SIZE = '#d29922';
const C_DIM = '#6e7681';
const C_2xx = '#3fb950';
const C_3xx = '#d29922';
const C_4xx = '#7d8ca3';
const C_5xx = '#ff7b72';

function scColor(code) {
  const c = String(code).charAt(0);
  if (c === '2') return C_2xx;
  if (c === '3') return C_3xx;
  if (c === '5') return C_5xx;
  return C_4xx;
}

function dim(s) { return '<span style="color:' + C_DIM + '">' + esc(s) + '</span>'; }

function colorizeLine(text) {
  if (!text) return '';
  if (text.indexOf('\u001b') >= 0) return ansiToHtml(text);

  // dirsearch: [23:20:59] 200 -  12KB - /www.zip
  let m = text.match(/^(\[\d{2}:\d{2}:\d{2}\])\s+(\d{3})\s+-\s+(\S+)\s+-\s+(.*)$/);
  if (m) {
    return '<span style="color:' + C_TIME + '">' + esc(m[1]) + '</span> '
      + '<span style="color:' + scColor(m[2]) + ';font-weight:600">' + esc(m[2]) + '</span>'
      + dim(' - ')
      + '<span style="color:' + C_SIZE + '">' + esc(m[3]) + '</span>'
      + dim(' - ')
      + '<span style="color:' + C_PATH + '">' + esc(m[4]) + '</span>';
  }

  // dirsearch: [23:20:59] 403 - 321B - /cgi-bin/（同上，兼容少空格）
  m = text.match(/^(\[\d{2}:\d{2}:\d{2}\])\s+(\d{3})\s*-\s*(\S+)\s*-\s*(.*)$/);
  if (m) {
    return '<span style="color:' + C_TIME + '">' + esc(m[1]) + '</span> '
      + '<span style="color:' + scColor(m[2]) + ';font-weight:600">' + esc(m[2]) + '</span>'
      + dim(' - ')
      + '<span style="color:' + C_SIZE + '">' + esc(m[3]) + '</span>'
      + dim(' - ')
      + '<span style="color:' + C_PATH + '">' + esc(m[4]) + '</span>';
  }

  // sqlmap 的日志行 [12:34:56] [INFO] ...
  m = text.match(/^(\[\d{2}:\d{2}:\d{2}\])\s*\[(\w+)\]\s*(.*)$/);
  if (m) {
    const lv = m[2].toUpperCase();
    const lc = lv === 'ERROR' || lv === 'CRITICAL' ? C_5xx
             : lv === 'WARNING' ? C_3xx
             : lv === 'INFO' ? '#79c0ff' : C_DIM;
    return '<span style="color:' + C_TIME + '">' + esc(m[1]) + '</span> '
      + '<span style="color:' + lc + ';font-weight:600">[' + esc(m[2]) + ']</span> '
      + esc(m[3]);
  }

  // 配置摘要行
  m = text.match(/^(Extensions|Target|HTTP method|Threads|Wordlist size|Extensions|Payloads):(.*)$/);
  if (m) {
    return '<span style="color:' + C_DIM + '">' + esc(m[1]) + ':</span>'
      + '<span style="color:#d6deeb">' + esc(m[2]) + '</span>';
  }

  // Scanning: / Task Completed 这类标题
  if (/^\[\d{2}:\d{2}:\d{2}\]\s+Scanning:\s*$/.test(text)) {
    return '<span style="color:' + C_TIME + '">' + esc(text) + '</span>';
  }
  if (/^(Task Completed|Done|Finished)\s*$/.test(text)) {
    return '<span style="color:' + C_2xx + ';font-weight:600">' + esc(text) + '</span>';
  }

  return esc(text);
}

function ansiToHtml(text) {
  if (!text || text.indexOf('\u001b') < 0) return esc(text);
  let html = '';
  let last = 0;
  let depth = 0;
  const re = /\u001b\[([0-9;]*)([A-Za-z])/g;
  let m;
  while ((m = re.exec(text))) {
    html += esc(text.slice(last, m.index));
    last = m.index + m[0].length;
    if (m[2] !== 'm') continue;            // 非颜色控制码直接丢掉
    const codes = m[1] ? m[1].split(';').map(Number) : [0];
    for (const c of codes) {
      if (c === 0) {
        while (depth > 0) { html += '</span>'; depth--; }
      } else if (c === 1) {
        html += '<span style="font-weight:600">';
        depth++;
      } else if (c === 22) {
        if (depth > 0) { html += '</span>'; depth--; }
      } else if (ANSI_COLOR[c]) {
        html += '<span style="color:' + ANSI_COLOR[c] + '">';
        depth++;
      }
    }
  }
  html += esc(text.slice(last));
  while (depth > 0) { html += '</span>'; depth--; }
  return html;
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function basename(p) {
  if (!p) return '';
  const s = String(p).replace(/\\/g, '/');
  return s.slice(s.lastIndexOf('/') + 1);
}

/* ---------------------------------------------------------- 输出 */
function append(text, cls) {
  const t = CT();
  if (!t) return;
  const div = document.createElement('div');
  div.className = 'line ' + (cls || '');
  div.textContent = text;
  t.outEl.appendChild(div);
  if (t === CT()) t.outEl.scrollTop = t.outEl.scrollHeight;
  while (t.outEl.children.length > 5000) t.outEl.removeChild(t.outEl.firstChild);
}

function appendTo(tab, text, cls, progress) {
  const out = tab.outEl;
  if (progress) {
    const last = out.lastElementChild;
    if (last && last.dataset.progress === '1') {
      last.innerHTML = colorizeLine(text);
      last.className = 'line progress';
      if (tab === CT()) out.scrollTop = out.scrollHeight;
      return;
    }
    const div = document.createElement('div');
    div.className = 'line progress';
    div.dataset.progress = '1';
    div.innerHTML = colorizeLine(text);
    out.appendChild(div);
    if (tab === CT()) out.scrollTop = out.scrollHeight;
    while (out.children.length > 5000) out.removeChild(out.firstChild);
    return;
  }
  const last = out.lastElementChild;
  if (last && last.dataset.progress === '1') delete last.dataset.progress;
  const div = document.createElement('div');
  div.className = 'line ' + (cls || '');
  div.innerHTML = colorizeLine(text);
  out.appendChild(div);
  if (tab === CT()) out.scrollTop = out.scrollHeight;
  while (out.children.length > 5000) out.removeChild(out.firstChild);
}

function classify(t) {
  const raw = t || '';
  const m = raw.match(/^\s*(?:\[\d{2}:\d{2}:\d{2}\]\s*)?(\d{3})\s+-\s+/);
  if (m) {
    const c = m[1].charAt(0);
    if (c === '2') return 'st2';
    if (c === '3') return 'st3';
    if (c === '4') return 'st4';
    if (c === '5') return 'st5';
  }
  let s = raw.toLowerCase();
  s = s.replace(/errors?\s*[:=]\s*\d+/g, '');
  if (/(traceback|error|exception|失败|denied|fatal)/.test(s)) return 'err';
  if (/(warning|warn|警告|deprecated)/.test(s)) return 'warn';
  return '';
}

/* ---------------------------------------------------------- toast */
function toast(msg, kind) {
  let box = document.getElementById('toastBox');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toastBox';
    box.className = 'toast-box';
    document.body.appendChild(box);
  }
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || '');
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, 2800);
}

function welcomeCard(tab) {
  const el = document.createElement('div');
  el.className = 'welcome';
  el.innerHTML = '<div class="w-logo">⚡</div>'
    + '<h1>web-fast</h1>'
    + '<p>左边点一个工具开始。每个工具开一个标签，dirsearch 和 sqlmap 可以同时跑。</p>'
    + '<div class="w-keys">'
    + '<span><kbd>Tab</kbd> 选中候选</span>'
    + '<span><kbd>↑</kbd><kbd>↓</kbd> 切换</span>'
    + '<span><kbd>Esc</kbd> 关闭候选</span>'
    + '<span><kbd>Ctrl</kbd>+<kbd>C</kbd> 停止</span>'
    + '</div>';
  tab.outEl.appendChild(el);
}

/* ---------------------------------------------------------- 标签页 */
function newTab(toolData) {
  const id = ++state.seqTab;
  const el = document.createElement('div');
  el.className = 'output';
  $('#outputWrap').appendChild(el);
  const tab = {
    id,
    toolId: toolData ? toolData.id : null,
    title: toolData ? toolData.name : 'shell',
    cwd: toolData ? toolData.cwd : state.appRoot,
    tool: toolData || null,
    outEl: el,
    input: '',
    history: [],
    histIdx: -1,
    running: false,
    progress: '',
    runId: null,
    es: null,
    picker: { active: false, kind: 'param', items: [], index: 0, ctx: null },
  };
  state.tabs.push(tab);
  return tab;
}

function renderTabs() {
  const box = $('#tabs');
  box.innerHTML = '';
  state.tabs.forEach((t, i) => {
    const el = document.createElement('div');
    el.className = 'tab'
      + (i === state.active ? ' active' : '')
      + (t.running ? ' busy' : '')
      + (t.tool && !t.tool.ready ? ' off' : '');
    const prog = t.running && t.progress ? '  ' + t.progress : '';
    el.innerHTML = '<span class="tdot"></span>'
      + '<span class="tname">' + esc(t.title) + esc(prog) + '</span>'
      + (state.tabs.length > 1 ? '<span class="tx" title="关闭">×</span>' : '');
    el.onclick = ev => {
      if (ev.target.classList.contains('tx')) { closeTab(t.id); return; }
      activateTab(i);
    };
    box.appendChild(el);
  });
}

function activateTab(index) {
  if (index < 0 || index >= state.tabs.length) return;
  const old = CT();
  if (old) old.input = cmdEl().value;
  hidePicker();

  state.active = index;
  const t = CT();
  for (const tt of state.tabs) {
    tt.outEl.classList.toggle('active', tt === t);
  }
  renderTabs();
  cmdEl().value = t.input || '';
  cmdEl().setSelectionRange(cmdEl().value.length, cmdEl().value.length);
  cmdEl().classList.toggle('busy', !!t.running);
  $('#btnStop').disabled = !t.running;
  updatePrompt();
  updateToolbar(t);
  t.outEl.scrollTop = t.outEl.scrollHeight;
  focusCmd();
}

function closeTab(id) {
  const i = state.tabs.findIndex(x => x.id === id);
  if (i < 0) return;
  const t = state.tabs[i];
  if (t.running) {
    if (!confirm('这个标签还有命令在跑，结束并关闭？')) return;
    stopRun(t);
  }
  if (t.es) { try { t.es.close(); } catch (e) {} }
  t.outEl.remove();
  state.tabs.splice(i, 1);
  if (!state.tabs.length) {
    const nt = newTab(null);
    state.active = state.tabs.index ? 0 : 0;
    state.active = 0;
    renderTabs();
    activateTab(0);
    return;
  }
  state.active = Math.min(i, state.tabs.length - 1);
  renderTabs();
  activateTab(state.active);
}

function updateToolbar(t) {
  if (!t || !t.tool) {
    $('#toolName').textContent = t ? t.title : '未选择工具';
    $('#toolPath').textContent = t ? t.cwd : '';
    $('#toolBadge').classList.add('hidden');
    return;
  }
  const d = t.tool;
  $('#toolName').textContent = d.name;
  $('#toolPath').textContent = d.cwd;
  const b = $('#toolBadge');
  b.classList.remove('hidden');
  b.classList.toggle('off', !d.ready);
  b.textContent = d.ready ? '● 就绪' : '○ ' + d.status;
}

function updatePrompt() {
  const t = CT();
  $('#prompt').textContent = 'PS ' + ((t && t.cwd) || '') + '>';
}

function focusCmd() { cmdEl().focus(); }

/* ---------------------------------------------------------- 工具列表 */
async function loadTools() {
  const d = await (await fetch('/api/tools')).json();
  state.tools = d.tools || [];
  renderTools();
  $('#readyStat').textContent = d.ready + '/' + d.total + ' 就绪';
}

function renderTools() {
  const q = ($('#search').value || '').toLowerCase();
  const nav = $('#toolList');
  nav.innerHTML = '';
  const groups = {};
  for (const t of state.tools) {
    const hay = (t.id + ' ' + t.name + ' ' + t.category + ' ' + t.summary).toLowerCase();
    if (q && !hay.includes(q)) continue;
    (groups[t.category] = groups[t.category] || []).push(t);
  }
  const cats = Object.keys(groups);
  if (!cats.length) {
    nav.innerHTML = '<div class="empty">没有匹配的工具</div>';
    return;
  }
  const cur = CT();
  for (const cat of cats) {
    const h = document.createElement('div');
    h.className = 'cat';
    h.textContent = cat;
    nav.appendChild(h);
    for (const t of groups[cat]) {
      const el = document.createElement('div');
      el.className = 'tool'
        + (t.ready ? '' : ' off')
        + (cur && cur.toolId === t.id ? ' active' : '');
      el.innerHTML = '<span class="dot"></span>'
        + '<span class="tname">' + esc(t.id) + '</span>'
        + (t.ready ? '' : '<span class="tstat">未就绪</span>');
      el.onclick = () => selectTool(t.id);
      nav.appendChild(el);
    }
  }
}

async function selectTool(id) {
  const d = await (await fetch('/api/tool?id=' + encodeURIComponent(id))).json();
  if (d.error) { append(d.error, 'err'); return; }
  const cur = CT();
  let tab;
  if (cur && !cur.toolId) {
    tab = cur;
  } else {
    tab = newTab(d);
    state.active = state.tabs.length - 1;
    activateTab(state.active);
    tab = CT();
  }
  bindToolToTab(tab, d);
  renderTabs();
  renderTools();
}

function bindToolToTab(tab, d) {
  tab.toolId = d.id;
  tab.tool = d;
  tab.cwd = d.cwd;
  tab.title = d.name;
  tab.picker = { active: false, kind: 'param', items: [], index: 0, ctx: null };
  if (tab === CT()) {
    updatePrompt();
    updateToolbar(tab);
    banner(tab, d);
    prefill(tab, d);
    focusCmd();
  }
}

function banner(tab, t) {
  appendTo(tab, '─'.repeat(64), 'banner');
  appendTo(tab, t.name + '   ' + t.category, 'bold');
  if (t.summary) appendTo(tab, t.summary, 'dim');
  appendTo(tab, '目录  ' + t.cwd, 'dim');
  const names = t.params.slice(0, 10).map(p => p.name).join('  ');
  if (names) appendTo(tab, '常用  ' + names, 'info');
  appendTo(tab, '敲 - 出参数候选 · Tab 选中 · ↑↓ 切换 · params 看全部 · help 看命令', 'dim');
  if (!t.ready) appendTo(tab, '[未就绪] ' + t.status, 'warn');
}

function prefill(tab, t) {
  let text = '';
  if (t.runner === 'python') text = 'python ' + basename(t.entry) + ' ';
  else if (t.runner === 'module') text = 'python -m ' + t.entry + ' ';
  else text = basename(t.entry) + ' ';
  cmdEl().value = text;
  cmdEl().setSelectionRange(text.length, text.length);
  tab.input = text;
}

/* ---------------------------------------------------------- 输入分析 */
function tokenize(s) {
  const out = [];
  const re = /[^\s]+/g;
  let m;
  while ((m = re.exec(s))) out.push({ text: m[0], start: m.index, end: m.index + m[0].length });
  return out;
}


function quoteRule(p, value) {
  const q = (p && p.quote) || '';
  if (q === '1') return true;
  if (q === '0') return false;
  if (p && (p.type === 'file' || p.type === 'dir' || p.type === 'path')) return true;
  if (p && p.source && (p.source.indexOf('glob:') === 0 || p.source.indexOf('dir:') === 0)) return true;
  return /\s/.test(value || '');
}

function paramOf(name) {
  const t = CT();
  if (!t || !t.tool) return null;
  return t.tool.params.find(x => x.name === name) || null;
}

function isParamName(name) {
  return !!paramOf(name);
}

function analyze() {
  const t = CT();
  if (!t || !t.tool) return null;
  const el = cmdEl();
  const before = el.value.slice(0, el.selectionStart);
  const endsSpace = /\s$/.test(before);
  const toks = tokenize(before);
  const last = toks[toks.length - 1];
  if (!last) return null;

  if (!endsSpace && last.text.startsWith('-')) {
    const eq = last.text.indexOf('=');
    if (eq > 0) {
      const pname = last.text.slice(0, eq);
      if (isParamName(pname)) {
        let frag = last.text.slice(eq + 1);
        if ((frag.startsWith('"') && frag.endsWith('"')) ||
            (frag.startsWith("'") && frag.endsWith("'"))) {
          frag = frag.slice(1, -1);
        }
        return { mode: 'value', param: pname, frag: frag, head: before.slice(0, last.start) + pname };
      }
    }
    return { mode: 'param', token: last.text, head: before.slice(0, last.start) };
  }
  if (!endsSpace && !last.text.startsWith('-') && toks.length >= 2) {
    const prev = toks[toks.length - 2];
    if (prev.text.startsWith('-') && isParamName(prev.text)) {
      let frag = last.text;
      if ((frag.startsWith('"') && frag.endsWith('"')) ||
          (frag.startsWith("'") && frag.endsWith("'"))) {
        frag = frag.slice(1, -1);
      }
      return { mode: 'value', param: prev.text, frag: frag, head: before.slice(0, prev.end) };
    }
  }
  if (endsSpace && last.text.startsWith('-') && isParamName(last.text)) {
    return { mode: 'value', param: last.text, frag: '', head: before.slice(0, last.end) };
  }
  return null;
}

function subseq(needle, hay) {
  let i = 0;
  for (const ch of hay) {
    if (ch === needle[i]) i++;
    if (i >= needle.length) return true;
  }
  return needle.length === 0;
}

/* ---------------------------------------------------------- 候选 */
async function refreshPicker() {
  const t = CT();
  const a = analyze();
  if (!t || !t.tool || !a) { hidePicker(); return; }
  if (a.mode === 'param') {
    const frag = a.token.replace(/^-+/, '').toLowerCase();
    const rows = t.tool.params
      .map((p, i) => ({ p, i, n: p.name.replace(/^-+/, '').toLowerCase() }))
      .filter(x => !frag || x.n.startsWith(frag) || subseq(frag, x.n))
      .sort((x, y) => {
        const rx = (!frag || x.n.startsWith(frag)) ? 0 : 1;
        const ry = (!frag || y.n.startsWith(frag)) ? 0 : 1;
        return rx - ry || x.i - y.i;
      })
      .map(x => ({ name: x.p.name, label: x.p.label || '', tag: x.p.source ? '可选' : '' }));
    showPicker('param', rows, a);
  } else {
    const key = t.tool.id + '|' + a.param;
    const seq = ++state.seqReq;
    let items = state.candCache[key];
    if (!items) {
      try {
        const r = await fetch('/api/candidates?tool=' + encodeURIComponent(t.tool.id)
          + '&param=' + encodeURIComponent(a.param));
        items = ((await r.json()).items) || [];
        state.candCache[key] = items;
      } catch (e) { items = []; }
    }
    if (seq !== state.seqReq) return;
    let rows = items;
    if (a.frag) {
      const seg = a.frag.split(',').pop() || '';
      const f = seg.trim().toLowerCase();
      if (f) {
        rows = items.filter(x => x.label.toLowerCase().includes(f) || x.value.toLowerCase().includes(f));
      }
    }
    showPicker('value', rows, a);
  }
}

function showPicker(kind, rows, ctx) {
  const t = CT();
  if (!rows || !rows.length) { hidePicker(); return; }
  t.picker.active = true;
  t.picker.kind = kind;
  t.picker.items = rows;
  t.picker.ctx = ctx;
  if (t.picker.index >= rows.length) t.picker.index = 0;
  renderPicker();
}

function renderPicker() {
  const t = CT();
  if (!t) return;
  const st = t.picker;
  const box = $('#picker');
  box.innerHTML = '<div class="plist"></div><div class="pfoot"></div>';
  const list = box.querySelector('.plist');
  const foot = box.querySelector('.pfoot');
  st.items.forEach((it, i) => {
    const d = document.createElement('div');
    d.className = 'pitem' + (i === st.index ? ' sel' : '');
    if (st.kind === 'param') {
      d.innerHTML = '<span class="pname">' + esc(it.name) + '</span>'
        + '<span class="plabel">' + esc(it.label) + '</span>'
        + (it.tag ? '<span class="ptag">' + esc(it.tag) + '</span>' : '');
    } else {
      d.innerHTML = '<span class="pname">' + esc(it.label) + '</span>';
    }
    d.onmouseenter = () => { st.index = i; renderPicker(); };
    d.onmousedown = ev => { ev.preventDefault(); pick(); };
    list.appendChild(d);
  });
  foot.innerHTML = '<span>' + st.items.length + ' 项</span>'
    + '<span>Tab 选中 · ↑↓ 切换 · Esc 关闭</span>';
  box.classList.remove('hidden');
  const sel = list.querySelector('.pitem.sel');
  if (sel) sel.scrollIntoView({ block: 'nearest' });
}

function hidePicker() {
  const t = CT();
  if (t) {
    t.picker.active = false;
    t.picker.items = [];
    t.picker.index = 0;
  }
  $('#picker').classList.add('hidden');
}

function pick() {
  const t = CT();
  if (!t) return false;
  const st = t.picker;
  if (!st.active || !st.items.length) return false;
  const it = st.items[st.index];
  const el = cmdEl();
  let text, cursor;

  if (st.kind === 'param') {
    const p = paramOf(it.name);
    const needsValue = !!p && p.type !== 'bool' && p.type !== 'positional';
    const isLong = it.name.startsWith('--');
    const wantQuote = p ? quoteRule(p, '') : false;
    if (!needsValue) {
      text = st.ctx.head + it.name + ' ';
      cursor = text.length;
    } else if (isLong) {
      text = st.ctx.head + it.name + '=';
      cursor = text.length;
    } else if (wantQuote) {
      text = st.ctx.head + it.name + ' ""';
      cursor = text.length - 1;
    } else {
      text = st.ctx.head + it.name + ' ';
      cursor = text.length;
    }
    hidePicker();
    el.value = text;
    el.setSelectionRange(cursor, cursor);
    if (needsValue) refreshPicker();
    return true;
  }

  if (it.value === '__browse__') {
    hidePicker();
    append('[提示] 浏览器里弹不出系统文件框，直接把完整路径打进去', 'warn');
    return true;
  }

  const p = paramOf(st.ctx.param);
  const isLong = st.ctx.param.startsWith('--');
  const sep = isLong ? '=' : ' ';
  if (p && p.source_multi) {
    let tail = el.value.slice(st.ctx.head.length).trim();
    tail = tail.replace(/^=\s*/, '').replace(/^["']/, '').replace(/["']$/, '');
    const picked = tail.replace(/,+$/, '').split(',').map(x => x.trim()).filter(Boolean);
    if (picked.indexOf(it.value) >= 0) {
      // 已经选过了，不重复加
      hidePicker();
      return true;
    }
    let joined;
    if (!tail) {
      joined = it.value;
    } else if (tail.endsWith(',')) {
      joined = tail + it.value;
    } else {
      joined = tail + ',' + it.value;
    }
    text = st.ctx.head + sep + joined + ' ';
    cursor = text.length;
  } else {
    const needQuote = p ? quoteRule(p, it.value) : /\s/.test(it.value);
    const shown = needQuote ? '"' + it.value + '"' : it.value;
    text = st.ctx.head + sep + shown + ' ';
    cursor = text.length;
  }
  hidePicker();
  el.value = text;
  el.setSelectionRange(cursor, cursor);
  return true;
}

/* ---------------------------------------------------------- 执行 */
async function runLine(line) {
  const t = CT();
  if (!t) return;
  const body = { tool: t.toolId || '', cmdline: line };
  const d = await (await fetch('/api/run', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).json();
  if (d.error) { append(d.error, 'err'); return; }
  t.running = true;
  t.runId = d.run;
  if (t === CT()) {
    cmdEl().classList.add('busy');
    $('#btnStop').disabled = false;
  }
  renderTabs();
  let closed = false;
  const es = new EventSource('/api/stream/' + d.run);
  t.es = es;
  es.onmessage = ev => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.type === 'progress') {
      t.progress = m.text;
      if (t === CT()) {
        const st = $('#lblState') || $('#toolBadge');
        if (st) st.textContent = '◐ ' + m.text;
      }
      renderTabs();
      return;
    }
    if (m.type === 'line') appendTo(t, m.text, classify(m.text), false);
    else if (m.type === 'exit') {
      appendTo(t, '[退出码 ' + m.code + ']', m.code === 0 ? 'ok' : 'err');
      closed = true;
      es.close();
      finishRun(t);
    }
  };
  es.onerror = () => {
    if (closed) return;
    closed = true;
    try { es.close(); } catch (e) {}
    finishRun(t);
  };
}

function finishRun(tab) {
  tab.running = false;
  tab.es = null;
  tab.runId = null;
  tab.progress = '';
  renderTabs();
  if (tab.tool) {
    const b = $('#toolBadge');
    if (b && tab === CT()) {
      b.textContent = tab.tool.ready ? '● 就绪' : '○ ' + tab.tool.status;
      b.classList.toggle('off', !tab.tool.ready);
    }
  }
  if (tab === CT()) {
    cmdEl().classList.remove('busy');
    $('#btnStop').disabled = true;
    focusCmd();
  }
}

async function stopRun(tab) {
  const t = tab || CT();
  if (!t || !t.running || !t.runId) return;
  appendTo(t, '[正在结束进程…]', 'warn');
  await fetch('/api/stop', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run: t.runId }),
  });
}

/* ---------------------------------------------------------- 内置命令 */
function helpText() {
  const rows = [
    ['help', '这份说明'],
    ['params [关键词]', '列出当前工具全部参数'],
    ['use <工具名>', '在当前标签切到另一个工具'],
    ['cd <目录>', '切换当前标签的目录'],
    ['pwd', '显示当前目录'],
    ['clear / cls', '清空当前标签输出'],
    ['Tab', '选中候选 / 补全参数名'],
    ['↑ ↓', '候选之间切换，没候选时翻历史'],
    ['Esc', '关闭候选'],
    ['Ctrl+C', '结束当前命令'],
    ['+ (标签栏)', '开一个新标签，两个题同时跑也不打架'],
    ['其它', '当 PowerShell 命令执行'],
  ];
  append('内置命令', 'bold');
  for (const [k, v] of rows) append('  ' + k.padEnd(20, ' ') + v);
}

async function paramsText(q) {
  const t = CT();
  if (!t || !t.tool) { append('先选一个工具', 'warn'); return; }
  const query = (q || '').trim();
  let rows = t.tool.params;
  if (query) {
    const ql = query.toLowerCase();
    rows = rows.filter(p => (p.name + p.label + p.help + p.group + (p.tags || []).join(' '))
      .toLowerCase().includes(ql));
  }
  if (!rows.length) { append('没有匹配「' + query + '」的参数', 'warn'); return; }
  append(t.tool.id + ' 参数（' + rows.length + ' 个）', 'bold');
  let g = null;
  for (const p of rows) {
    if (p.group !== g) { g = p.group; append('', ''); append('  [' + g + ']', 'info'); }
    append('  ' + (p.required ? '*' : ' ') + p.name.padEnd(18, ' ')
      + (p.label || '').padEnd(12, ' ') + (p.help || ''), '');
    if (p.example) append('   ' + ' '.repeat(18) + '例: ' + p.example, 'dim');
  }
  append('', '');
}

async function doCd(arg) {
  const t = CT();
  const r = await fetch('/api/cd', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: arg, cwd: t.cwd }),
  });
  const d = await r.json();
  if (d.ok) { t.cwd = d.cwd; updatePrompt(); }
  else append('目录不存在: ' + d.cwd, 'err');
}

/* ---------------------------------------------------------- 提交 */
async function submit() {
  const t = CT();
  if (!t) return;
  const el = cmdEl();
  const line = el.value.trim();
  if (t.running) {
    const text = el.value;
    append('[stdin] ' + text, 'dim');
    await fetch('/api/stdin', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run: t.runId, text: text + '\n' }),
    });
    el.value = '';
    return;
  }
  if (!line) return;
  t.history.push(line);
  t.histIdx = t.history.length;
  append('PS ' + t.cwd + '> ' + line, 'cmd');
  el.value = '';
  hidePicker();

  const parts = line.split(/\s+/);
  const h = parts[0].toLowerCase();
  const rest = parts.slice(1);
  if (h === 'clear' || h === 'cls') { t.outEl.innerHTML = ''; return; }
  if (h === 'help' || h === '?') { helpText(); return; }
  if (h === 'params' || h === 'param') { paramsText(rest.join(' ')); return; }
  if (h === 'use') { if (rest[0]) selectTool(rest[0]); else append('用法: use <工具>', 'warn'); return; }
  if (h === 'cd') { doCd(rest.join(' ')); return; }
  if (h === 'pwd') { append(t.cwd); return; }
  if (h === 'exit' || h === 'quit') { append('关标签或关页面即可退出', 'dim'); return; }
  await runLine(line);
}

/* ---------------------------------------------------------- 参数表 */
function openParams() {
  const t = CT();
  if (!t || !t.tool) { append('先选一个工具', 'warn'); return; }
  $('#modalTitle').textContent = t.tool.id + ' · 参数表';
  $('#modalSearch').value = '';
  fillParams('');
  $('#modal').classList.remove('hidden');
  setTimeout(() => $('#modalSearch').focus(), 30);
}

function fillParams(q) {
  const t = CT();
  if (!t || !t.tool) return;
  const tb = $('#paramTable tbody');
  tb.innerHTML = '';
  const ql = (q || '').toLowerCase();
  for (const p of t.tool.params) {
    const hay = (p.name + p.label + p.help + p.group + (p.tags || []).join(' ')).toLowerCase();
    if (ql && !hay.includes(ql)) continue;
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + esc(p.name) + '</td>'
      + '<td>' + esc(p.label) + '</td>'
      + '<td>' + esc(p.group) + '</td>'
      + '<td>' + esc(p.help) + '</td>';
    tr.onclick = () => {
      const el = cmdEl();
      let txt = el.value;
      if (txt && !/\s$/.test(txt)) txt += ' ';
      el.value = txt + p.name + ' ';
      el.setSelectionRange(el.value.length, el.value.length);
      closeModal();
      focusCmd();
      refreshPicker();
    };
    tb.appendChild(tr);
  }
  $('#modalHint').textContent = '共 ' + tb.children.length + ' 项 · 点一行插入到命令行';
}

function closeModal() { $('#modal').classList.add('hidden'); }

/* ---------------------------------------------------------- 选择文件夹 */
async function pickFolder(current) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
    try {
      const p = await window.pywebview.api.pick_folder(current || '');
      return p || '';
    } catch (e) {}
  }
  try {
    const r = await fetch('/api/pickfolder', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ initial: current || '' }),
    });
    if (r.status === 404) {
      toast('后台服务是旧版本，没有「选择文件夹」接口，重启应用即可', 'err');
      return '';
    }
    const d = await r.json();
    return d.path || '';
  } catch (e) {
    toast('打不开文件夹对话框：' + e, 'err');
    return '';
  }
}

/* ---------------------------------------------------------- 打开目录 */
async function openPath(path) {
  if (!path) {
    toast('没有可打开的目录', 'err');
    return;
  }
  try {
    const r = await fetch('/api/opendir', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: path }),
    });
    if (r.status === 404) {
      toast('后台服务是旧版本，没有「打开目录」接口。关掉窗口重新打开应用即可', 'err');
      return;
    }
    const d = await r.json();
    if (d.ok) toast('已打开 ' + d.path, 'ok');
    else toast('打开失败：' + d.error, 'err');
  } catch (e) {
    toast('连不上后台服务：' + e, 'err');
  }
}

function openDir() {
  const t = CT();
  if (!t) return;
  openPath((t.tool && t.tool.cwd) || t.cwd);
}

/* ---------------------------------------------------------- 查找 */
let findHits = [];
let findIdx = -1;

function findClear() {
  const t = CT();
  if (t) {
    for (const el of t.outEl.querySelectorAll('.line.hit, .line.hit-cur')) {
      el.classList.remove('hit', 'hit-cur');
    }
  }
  findHits = [];
  findIdx = -1;
  $('#findCount').textContent = '';
}

function findRun(q) {
  const t = CT();
  findClear();
  if (!t || !q) return;
  const ql = q.toLowerCase();
  findHits = [...t.outEl.querySelectorAll('.line')]
    .filter(el => el.textContent.toLowerCase().indexOf(ql) >= 0);
  for (const el of findHits) el.classList.add('hit');
  if (!findHits.length) {
    $('#findCount').textContent = '0 条';
    return;
  }
  findIdx = 0;
  findGoto();
}

function findGoto() {
  findHits.forEach((el, i) => el.classList.toggle('hit-cur', i === findIdx));
  if (findHits[findIdx]) findHits[findIdx].scrollIntoView({ block: 'center' });
  $('#findCount').textContent = (findIdx + 1) + '/' + findHits.length;
}

function findStep(d) {
  if (!findHits.length) return;
  findIdx = (findIdx + d + findHits.length) % findHits.length;
  findGoto();
}

function findOpen() {
  $('#findBar').classList.remove('hidden');
  const inp = $('#findInput');
  inp.focus();
  inp.select();
  if (inp.value) findRun(inp.value);
}

function findClose() {
  $('#findBar').classList.add('hidden');
  findClear();
  focusCmd();
}

/* ---------------------------------------------------------- 设置 */
let settingsState = { data: null, current: null };

async function openSettings() {
  const d = await (await fetch('/api/settings')).json();
  settingsState.data = d;
  $('#cfgAppRoot').textContent = d.app_root;
  const nav = $('#settingsTools');
  nav.innerHTML = '';
  for (const t of d.tools) {
    const el = document.createElement('div');
    el.className = 'stool' + (t.ready ? '' : ' off');
    el.dataset.tool = t.id;
    el.innerHTML = '<span class="dot"></span><span class="sid">' + esc(t.id) + '</span>';
    el.onclick = () => pickSettingTool(t.id);
    nav.appendChild(el);
  }
  $('#settingsModal').classList.remove('hidden');
  const cur = CT();
  const first = d.tools.find(t => cur && cur.toolId && t.id === cur.toolId) || d.tools[0];
  if (first) pickSettingTool(first.id);
}

function fieldRow(label, key, value, help, exists) {
  const wrap = document.createElement('div');
  wrap.className = 'field';
  const k = key === '__cwd__' ? 'root' : key;
  const openBtn = value
    ? ' <button class="mini" data-open="' + esc(value) + '">打开</button>'
    : '';
  let stat = '';
  if (key !== '__cwd__') {
    if (!value) {
      stat = '<span class="s-bad">还没有设置，直接填路径</span>';
    } else if (exists) {
      stat = '<span class="s-ok">✓ 目录存在</span>' + openBtn;
    } else {
      stat = '<span class="s-bad">⚠ 目录不存在</span>'
        + ' <button class="mini" data-mkdir="' + esc(value) + '">创建这个目录</button>';
    }
  }
  const rootOpen = (key === '__cwd__' && value)
    ? '<div class="fstat">' + openBtn + '</div>' : '';
  wrap.innerHTML = '<label>' + esc(label) + '<span class="k">' + esc(k) + '</span></label>'
    + '<div class="field-input">'
    + '<input data-key="' + esc(key) + '" value="' + esc(value || '') + '" spellcheck="false">'
    + '<button class="mini browse" data-browse="' + esc(key) + '">浏览…</button>'
    + '</div>'
    + (help ? '<div class="fh">' + esc(help) + '</div>' : '')
    + (stat ? '<div class="fstat">' + stat + '</div>' : '')
    + rootOpen;
  return wrap;
}

function pickSettingTool(id) {
  const d = settingsState.data;
  if (!d) return;
  const t = d.tools.find(x => x.id === id);
  if (!t) return;
  settingsState.current = id;
  for (const el of document.querySelectorAll('#settingsTools .stool')) {
    el.classList.toggle('active', el.dataset.tool === id);
  }
  $('#paneTitle').textContent = t.name;
  const st = $('#paneState');
  st.textContent = t.ready ? '● 就绪' : '○ ' + t.status;
  st.className = 'pane-state ' + (t.ready ? 'ok' : 'bad');

  const box = $('#paneFields');
  box.innerHTML = '';
  box.appendChild(fieldRow('工具根目录', '__cwd__', t.cwd,
    '工具安装目录。换电脑时路径里的用户名会自动重映射，只换用户名不用改。'));
  const subs = t.settings || [];
  for (const s of subs) {
    box.appendChild(fieldRow(s.label || s.key, s.key, s.value,
      (s.help || '') + (s.default ? '　(默认 ' + s.default + ')' : ''), s.exists));
  }
  if (!subs.length) {
    const tip = document.createElement('div');
    tip.className = 'fh';
    tip.style.padding = '12px 0';
    tip.textContent = '这个工具没有额外的子目录配置，改上面的工具根目录就行。';
    box.appendChild(tip);
  }
  $('#btnSaveTool').disabled = false;
}

async function saveCurrentTool() {
  const id = settingsState.current;
  if (!id) return;
  const box = $('#paneFields');
  const inputs = [...box.querySelectorAll('input[data-key]')];
  let cwd = '';
  const subs = {};
  for (const inp of inputs) {
    const k = inp.dataset.key;
    if (k === '__cwd__') cwd = inp.value.trim();
    else subs[k] = inp.value.trim();
  }
  const btn = $('#btnSaveTool');
  btn.disabled = true;
  btn.textContent = '保存中…';
  try {
    const r = await fetch('/api/settool', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: id, path: cwd, settings: subs }),
    });
    const d = await r.json();
    if (!d.ok) { toast(d.error || '保存失败', 'err'); return; }
    toast('已保存 · ' + (d.ready ? '就绪' : (d.status || '未就绪')), d.ready ? 'ok' : 'err');
    const t = settingsState.data.tools.find(x => x.id === id);
    if (t) {
      t.cwd = d.cwd;
      t.ready = d.ready;
      t.status = d.status;
      for (const s of (d.settings || [])) {
        const old = (t.settings || []).find(x => x.key === s.key);
        if (old) old.value = s.value;
      }
    }
    state.candCache = {};
    pickSettingTool(id);
    await loadTools();
    for (const tab of state.tabs) {
      if (tab.toolId === id) {
        const d2 = await (await fetch('/api/tool?id=' + encodeURIComponent(id))).json();
        if (!d2.error) {
          tab.tool = d2;
          tab.cwd = d2.cwd;
          if (tab === CT()) { updatePrompt(); updateToolbar(tab); }
        }
      }
    }
  } catch (e) {
    toast('保存失败：' + e, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = '保存这个工具';
  }
}

async function autoScan() {
  const btn = $('#btnScan');
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '扫描中…';
  try {
    const r = await fetch('/api/discover', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ depth: 4 }),
    });
    const d = await r.json();
    const map = {};
    for (const h of (d.found || [])) map[h.tool] = h.path;
    let n = 0;
    for (const t of settingsState.data.tools) {
      if (map[t.id]) { t.cwd = map[t.id]; n++; }
    }
    pickSettingTool(settingsState.current);
    toast(n ? ('扫到 ' + n + ' 个工具，填好了，点保存') : '没扫到工具', n ? 'ok' : 'err');
  } catch (e) {
    toast('扫描失败：' + e, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

/* ---------------------------------------------------------- 事件 */
function histPrev(dir) {
  const t = CT();
  if (!t || !t.history.length) return;
  t.histIdx = Math.max(0, Math.min(t.history.length, t.histIdx + dir));
  const el = cmdEl();
  el.value = t.histIdx < t.history.length ? t.history[t.histIdx] : '';
  el.setSelectionRange(el.value.length, el.value.length);
  hidePicker();
}

function bind() {
  $('#search').addEventListener('input', renderTools);

  const el = cmdEl();
  let keepScroll = null;
  el.addEventListener('scroll', () => { keepScroll = el.scrollLeft; });
  el.addEventListener('input', () => {
    const sl = keepScroll;
    refreshPicker();
    if (sl !== null) {
      requestAnimationFrame(() => { el.scrollLeft = sl; });
    }
  });
  el.addEventListener('click', () => refreshPicker());

  el.addEventListener('keydown', ev => {
    const t = CT();
    if (ev.key === 'Tab') {
      ev.preventDefault();
      if (!pick()) refreshPicker();
      return;
    }
    if (ev.key === 'Escape') { hidePicker(); return; }
    if (ev.key === 'ArrowDown') {
      ev.preventDefault();
      if (t && t.picker.active) {
        t.picker.index = Math.min(t.picker.items.length - 1, t.picker.index + 1);
        renderPicker();
      } else histPrev(-1);
      return;
    }
    if (ev.key === 'ArrowUp') {
      ev.preventDefault();
      if (t && t.picker.active) {
        t.picker.index = Math.max(0, t.picker.index - 1);
        renderPicker();
      } else histPrev(1);
      return;
    }
    if (ev.key === 'Enter') {
      ev.preventDefault();
      if (pick()) return;
      submit();
      return;
    }
    if (ev.key === 'c' && ev.ctrlKey) { stopRun(); return; }
  });

  $('#btnStop').onclick = () => stopRun();
  $('#btnParams').onclick = openParams;
  $('#btnDoctor').onclick = doctor;
  $('#btnOpenDir').onclick = openDir;
  $('#btnSettings').onclick = openSettings;
  $('#settingsClose').onclick = () => $('#settingsModal').classList.add('hidden');
  $('#btnSaveTool').onclick = saveCurrentTool;
  $('#btnScan').onclick = autoScan;
  $('#paneFields').addEventListener('click', async ev => {
    const bb = ev.target.closest('[data-browse]');
    if (bb) {
      const key = bb.dataset.browse;
      const inp = document.querySelector('#paneFields input[data-key="' + key + '"]');
      if (!inp) return;
      bb.disabled = true;
      const old = bb.textContent;
      bb.textContent = '…';
      try {
        const picked = await pickFolder(inp.value.trim());
        if (picked) {
          inp.value = picked.split(String.fromCharCode(92)).join('/');
          inp.focus();
        }
      } finally {
        bb.disabled = false;
        bb.textContent = old;
      }
      return;
    }
    const ob = ev.target.closest('[data-open]');
    if (ob) { openPath(ob.dataset.open); return; }
    const btn = ev.target.closest('[data-mkdir]');
    if (!btn) return;
    const path = btn.dataset.mkdir;
    btn.disabled = true;
    btn.textContent = '创建中…';
    try {
      const r = await fetch('/api/mkdir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      });
      const d = await r.json();
      if (d.ok) {
        toast('目录已创建：' + d.path, 'ok');
        pickSettingTool(settingsState.current);
      } else {
        toast('创建失败：' + d.error, 'err');
        btn.disabled = false;
        btn.textContent = '创建这个目录';
      }
    } catch (e) {
      toast('创建失败：' + e, 'err');
    }
  });

  $('#findInput').addEventListener('input', e => findRun(e.target.value));
  $('#findInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); findStep(e.shiftKey ? -1 : 1); }
    else if (e.key === 'Escape') { e.preventDefault(); findClose(); }
  });
  $('#findNext').onclick = () => findStep(1);
  $('#findPrev').onclick = () => findStep(-1);
  $('#findClose').onclick = findClose;

  $('#btnNewTab').onclick = () => {
    const t = newTab(null);
    state.active = state.tabs.length - 1;
    activateTab(state.active);
    append('新标签 · 从左侧点一个工具开始', 'dim');
  };
  $('#modalClose').onclick = closeModal;
  $('#modalSearch').addEventListener('input', e => fillParams(e.target.value));
  $('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      findOpen();
      return;
    }
    if (e.key === 'Escape') {
      if (!$('#modal').classList.contains('hidden')) { closeModal(); return; }
      if (!$('#settingsModal').classList.contains('hidden')) {
        $('#settingsModal').classList.add('hidden');
        return;
      }
      if (!$('#findBar').classList.contains('hidden')) { findClose(); return; }
    }
  });
}

async function doctor() {
  const t = CT();
  if (t) t.outEl.innerHTML = '';
  append('web-fast 体检', 'bold');
  await loadTools();
  for (const x of state.tools) {
    append((x.ready ? '  OK   ' : '  MISS ') + x.id.padEnd(12, ' ') + (x.ready ? '' : x.status),
      x.ready ? 'ok' : 'warn');
  }
  const ready = state.tools.filter(x => x.ready).length;
  append('', '');
  append(ready + '/' + state.tools.length + ' 个工具就绪', 'info');
}

/* ---------------------------------------------------------- 启动 */
(async function boot() {
  const bootTab = newTab(null);
  state.active = 0;
  bootTab.outEl.classList.add('active');
  welcomeCard(bootTab);

  await loadTools();
  const d = await (await fetch('/api/settings')).json();
  state.appRoot = d.app_root;
  bootTab.cwd = d.app_root;

  bind();
  updatePrompt();
  renderTabs();
  updateToolbar(bootTab);
  focusCmd();

  if (state.tools.filter(t => t.ready).length === 0) {
    append('没检测到任何可用工具。点右上角「设置」填路径，或者把工具放进 third_party/<工具名>/。', 'warn');
    append('', '');
  }
  const first = state.tools.find(t => t.ready) || state.tools[0];
  if (first && location.hash !== '#multi') await selectTool(first.id);

  if (location.hash.indexOf('#settings') === 0) {
    setTimeout(async () => {
      await openSettings();
      const which = location.hash.split(':')[1];
      if (which) pickSettingTool(which);
    }, 700);
  }
  (async () => {
    try {
      const r = await fetch('/api/opendir', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '' }),
      });
      if (r.status === 404) {
        const bar = document.createElement('div');
        bar.className = 'stale-bar';
        bar.innerHTML = '后台服务是旧版本（缺少新接口）· '
          + '<b>关掉这个窗口重新打开应用</b> 即可生效';
        document.body.appendChild(bar);
      }
    } catch (e) {}
  })();

  if (location.hash === '#multi') {
    setTimeout(async () => {
      await selectTool('sqlmap');
      await selectTool('dirsearch');
    }, 700);
  }
})();
