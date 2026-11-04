const $ = (s) => document.querySelector(s);
const api = (p) => fetch(p).then((r) => r.ok ? r.json() : Promise.reject(r.status));

/* 作者名：拼音 -> 中文（只做确定映射，其余按规则归一） */
const AUTHORS = {
  'Guanzhong Luo': '罗贯中', 'Xueqin Cao': '曹雪芹', "Cheng'en Wu": '吴承恩',
  "Nai'an Shi": '施耐庵', 'Songling Pu': '蒲松龄', 'Menglong Feng': '冯梦龙',
  'Mengchu Ling': '凌濛初', 'Jingzi Wu': '吴敬梓', 'Xiaoxiaosheng': '兰陵笑笑生',
  'Yu Li': '李渔', 'E Liu': '刘鹗', 'Xun Lu': '鲁迅', 'Jianren Wu': '吴趼人',
  'Boyuan Li': '李伯元', 'Wanchun Yu': '俞万春', 'Xixing Lu': '许仲琳',
  'Ruzhen Li': '李汝珍', 'Mei Yuan': '袁枚', 'Hanqing Guan': '关汉卿',
  'Xianzu Tang': '汤显祖', 'Yun Ji': '纪昀', 'Pu Zeng': '曾朴',
  'Bangqing Han': '韩邦庆', 'Quyuan': '屈原', 'Ming Gao': '高明', 'Sheng Hong': '洪昇',
  'Xuan Wu': '吴璿', 'Qingyuan Zhou': '周清原', 'Shiying Mu': '穆时英',
  'Tianhuazangzhuren': '天花藏主人', 'Baowenglaoren': '抱瓮老人',
  "Su'anzhuren": '苏庵主人', 'Juqizi': '菊畦子', 'Aiyuezhuren': '爱月主人',
  'Yuanhuyanshuisanren': '鸳湖烟水散人', 'Yunyangchichidaoren': '云阳嗤嗤道人',
  'Yukun Shi': '石玉昆', 'Wenkang': '文康', 'Renhu Chu': '褚人获',
  'Damu Xiong': '熊大木', 'Wuseshizhuren': '五色石主人', 'Qingxidaoren': '青溪道人',
  'Guanzhong Luo and Menglong Feng': '罗贯中 · 冯梦龙',
};

function authorName(a) {
  if (!a) return '佚名';
  if (AUTHORS[a]) return AUTHORS[a];
  // "active 1675-1695 Renhu Chu" -> "Renhu Chu"
  const m = a.match(/^(?:active|pseud\.?|ju ren|jin shi)[\s\d\-a-z.]*?([A-Z][A-Za-z' ]+)$/);
  if (m && AUTHORS[m[1].trim()]) return AUTHORS[m[1].trim()];
  if (/^(Anonymous|Unknown|Various)$/i.test(a)) return '佚名';
  if (/^(active|pseud|ju ren|jin shi)/i.test(a)) return '佚名';
  if (/[a-z]/i.test(a) && !/[\u4e00-\u9fa5]/.test(a)) return '佚名';
  return a;
}

const state = {
  all: [], sort: 'chars', q: '', cat: '',
  book: null, toc: [], ci: 0, loading: false, cn: 'en', ch: null,
  tr: false, tx: null, stopped: null,
};

function fmtChars(n) {
  if (n >= 10000) return (n / 10000).toFixed(n >= 100000 ? 0 : 1) + ' 万字';
  return n + ' 字';
}
const UNIT = { '回': '回', '章': '章', '卷': '卷', '篇': '篇', '节': '节', '单': '节' };

function bookSize(b) {
  if (b.lang === 'en') {
    const w = b.words || Math.round(b.chars / 5.6);
    return w >= 10000 ? (w / 10000).toFixed(w >= 100000 ? 0 : 1) + ' 万词' : w + ' 词';
  }
  return fmtChars(b.chars);
}

function render() {
  const q = state.q.trim().toLowerCase();
  let items = state.all;
  if (state.cat) items = items.filter(x => x.cat === state.cat);
  if (q) items = items.filter(x =>
    (x.title + ' ' + authorName(x.author)).toLowerCase().includes(q));

  const s = state.sort;
  items = [...items].sort((a, b) =>
    s === 'title' ? a.title.localeCompare(b.title, 'zh')
    : s === 'author' ? authorName(a.author).localeCompare(authorName(b.author), 'zh')
    : (b.w || b.chars) - (a.w || a.chars));

  $('#grid').innerHTML = items.map(b => `
    <button class="card" data-id="${b.id}">
      ${b.ok ? '' : '<span class="badge">残本</span>'}
      ${b.has_cn ? `<span class="cn">${b.lang === 'zh' ? '白' : '译'}</span>` : ''}
      ${b.lang === 'en' ? '<span class="en">EN</span>' : ''}
      <div class="t">${esc(b.title)}</div>
      <div class="a">${esc(authorName(b.author))}</div>
      <div class="s"><span class="c">${esc(b.cat)}</span>${b.has_cn ? `<span class="hascn">${b.lang === 'zh' ? '有白话' : '有译本'}</span> · ` : ''}${bookSize(b)} · ${b.n} ${UNIT[b.kind] || '节'}</div>
    </button>`).join('');

  $('#count').textContent = `${items.length} 本`;
  $('#empty').hidden = items.length > 0;
}

function renderCats(stats) {
  const list = [{ name: '', label: '全部', n: stats.books }]
    .concat(stats.cats.map(c => ({ name: c.name, label: c.name, n: c.n })));
  $('#cats').innerHTML = list.map(c =>
    `<button data-cat="${c.name}" class="${c.name === state.cat ? 'on' : ''}">${c.label}<i>${c.n}</i></button>`
  ).join('');
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

/* ---------- 阅读状态：以服务端为准，本地只留一个随机设备号 ---------- */
const CID_KEY = 'md:cid';
const cid = (() => {
  let v = '';
  try { v = localStorage.getItem(CID_KEY) || ''; } catch (e) { }
  if (!/^[A-Za-z0-9_-]{6,64}$/.test(v)) {
    v = 'd' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    try { localStorage.setItem(CID_KEY, v); } catch (e) { }
  }
  return v;
})();

function lsGet(k, def) {
  try { const v = localStorage.getItem(k); return v == null ? def : JSON.parse(v); } catch (e) { return def; }
}
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } }

/* 进度表 { 书号: {i, t} }，时间戳用于多设备合并 */
const getPos = (id) => {
  const m = lsGet('md:pos', {}) || {};
  const r = m[id];
  return (r && typeof r === 'object') ? (+r.i || 0) : (+r || 0);
};
function setPos(id, i) {
  const m = lsGet('md:pos', {}) || {};
  m[id] = { i, t: Date.now() };
  lsSet('md:pos', m);
  syncState();
}

let saveTimer = null;
function syncState() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const body = {
      recent: lsGet('md:recent', []) || [],
      pos: lsGet('md:pos', {}) || {},
      prefs: {
        theme: localStorage.getItem('md:theme') || 'day',
        fs: localStorage.getItem('md:fs') || '',
        cn: lsGet('md:cn', {}) || {},
      },
    };
    fetch('/api/state/' + cid, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).catch(() => { });
  }, 600);
}

/* 启动时把服务端状态并回本地，同一条取时间较新者 */
async function syncStateLoad() {
  try {
    const r = await fetch('/api/state/' + cid);
    if (!r.ok) return;
    const s = await r.json();
    const pos = lsGet('md:pos', {}) || {};
    Object.entries(s.pos || {}).forEach(([id, v]) => {
      const cur = pos[id];
      const t = (v && typeof v === 'object') ? (+v.t || 0) : 0;
      const ct = (cur && typeof cur === 'object') ? (+cur.t || 0) : 0;
      if (!cur || ct < t) pos[id] = v;
    });
    lsSet('md:pos', pos);

    const byId = {};
    (lsGet('md:recent', []) || []).concat(s.recent || []).forEach(x => {
      if (!x || !x.id) return;
      if (!byId[x.id] || (+x.t || 0) >= (+byId[x.id].t || 0)) byId[x.id] = x;
    });
    lsSet('md:recent', Object.values(byId).sort((a, b) => (+b.t || 0) - (+a.t || 0)).slice(0, 8));

    if (s.prefs && s.prefs.cn) {
      const cn = Object.assign({}, s.prefs.cn, lsGet('md:cn', {}) || {});
      lsSet('md:cn', cn);
    }
    return s;
  } catch (e) { return null; }
}

/* ---------- 继续阅读 ---------- */
function renderRecent() {
  let list = lsGet('md:recent', []) || [];
  list = list.filter(x => state.all.some(b => b.id === x.id)).slice(0, 6);
  if (!list.length) { $('#recent').hidden = true; return; }
  $('#recent').hidden = false;
  $('#recentList').innerHTML = list.map(x => {
    const b = state.all.find(v => v.id === x.id);
    const pct = Math.min(100, Math.round((x.ci + 1) / b.n * 100));
    return `<button class="rc" data-id="${x.id}">
      <span class="rt">${esc(b.title)}</span>
      <span class="rp">${pct}%</span>
      <span class="rbar"><i style="width:${pct}%"></i></span>
    </button>`;
  }).join('');
}

function pushRecent(id, ci) {
  let list = lsGet('md:recent', []) || [];
  list = list.filter(x => x.id !== id);
  list.unshift({ id, ci, t: Date.now() });
  lsSet('md:recent', list.slice(0, 8));
  syncState();
}

/* ---------- 阅读器 ---------- */

async function openBook(id, resume = true) {
  try {
    const meta = await api('/api/book/' + id);
    state.book = meta;
    state.toc = meta.toc;
    state.tr = !!meta.translate;
    $('#btitle').textContent = meta.title;
    const isEn = meta.lang === 'en';
    let tag = '';
    if (isEn) {
      tag = meta.has_cn ? ' · 英文原著（含中译）'
        : (meta.translate ? ' · 英文原著 · 可实时翻译' : ' · 英文原著');
    } else if (meta.can_modern) {
      tag = meta.has_cn ? ' · 文言原文（含白话译）' : ' · 文言原文 · 可今译';
    }
    $('#bauthor').textContent = authorName(meta.author) + ' · ' + meta.cat + tag;
    $('#text').dataset.lang = meta.lang;
    const cnModes = $('#cnModes');
    const canCn = meta.has_cn || meta.translate;
    cnModes.hidden = !canCn;
    state.cn = (!canCn) ? 'en' : ((lsGet('md:cn', {}) || {})[id] || 'en');
    // 英文书：英文/中文/双语；文言书：原文/白话/对照
    const labels = isEn ? ['英文', '中文', '双语'] : ['原文', '白话', '对照'];
    [...cnModes.children].forEach((x, i) => {
      x.textContent = labels[i];
      x.classList.toggle('on', x.dataset.cn === state.cn);
    });
    renderToc();

    let idx = 0;
    if (resume) {
      const saved = getPos(id);
      if (saved) idx = Math.min(+saved || 0, meta.toc.length - 1);
    }
    $('#reader').hidden = false;
    $('#shelf').style.display = 'none';
    document.body.style.overflow = 'hidden';
    await loadChapter(idx, true);
  } catch (e) {
    alert('加载失败：' + e);
  }
}

function renderToc() {
  const useCn = state.cn !== 'en';
  $('#tocList').innerHTML = state.toc.map(t => {
    const label = (useCn && t.ct) ? t.ct : t.t;
    return `<a href="#" data-i="${t.i}" title="${esc(label)}">${esc(label)}</a>`;
  }).join('');
  markToc();
}

function markToc() {
  const links = $('#tocList').children;
  for (let i = 0; i < links.length; i++) links[i].classList.toggle('on', i === state.ci);
}

async function loadChapter(idx, scrollTop = true) {
  if (state.loading) return;
  if (state.tx && state.tx.ctrl) { try { state.tx.ctrl.abort(); } catch (e) { } }
  state.tx = null;
  state.stopped = null;
  state.loading = true;
  try {
    const c = await api(`/api/book/${state.book.id}/ch/${idx}`);
    state.ci = idx;
    state.ch = c;
    renderChapter();
    $('#prevCh').disabled = idx === 0;
    $('#nextCh').disabled = idx >= state.toc.length - 1;
    $('#pnum').textContent = `${idx + 1} / ${state.toc.length}`;
    $('#progFill').style.width = ((idx + 1) / state.toc.length * 100) + '%';
    setPos(state.book.id, idx);
    pushRecent(state.book.id, idx);
    markToc();
    if (scrollTop) $('.paper').scrollTop = 0;
    const on = $('#tocList').children[idx];
    if (on) on.scrollIntoView({ block: 'nearest' });
  } finally {
    state.loading = false;
  }
}

// 文言书叫「今译」，英文书叫「翻译」，文案随书切换
const isModern = () => !!(state.book && state.book.mode === 'zh2modern');
const txWord = () => (isModern() ? '今译' : '翻译');

function renderChapter() {
  const c = state.ch;
  if (!c) return;
  const ta = $('#text');
  const mode = state.cn;
  ta.dataset.lang = (mode === 'en') ? state.book.lang : 'cn';
  const cn = c.cn || [];
  const tocCt = (state.toc[state.ci] || {}).ct || '';
  const cnTitle = tocCt || c.cnTitle;
  $('#ctitle').textContent = (mode !== 'en' && cnTitle) ? cnTitle : c.title;

  const total = c.paras.filter(p => p.trim()).length;
  const filled = cn.filter(p => p && p.trim()).length;
  paintTx(total, filled);

  if (mode === 'en') {
    ta.innerHTML = c.paras.map(p => `<p>${esc(p)}</p>`).join('');
    return;
  }
  if (mode === 'cn') {
    const out = c.paras.map((p, i) =>
      (cn[i] && cn[i].trim()) ? `<p>${esc(cn[i])}</p>` : '').join('');
    ta.innerHTML = out || `<p class="txempty">${
      state.tr ? `AI 正在${txWord()}本章，${txWord()}将逐段出现…` : `本章暂无${txWord()}。`}</p>`;
    return;
  }
  let html = '';
  for (let i = 0; i < c.paras.length; i++) {
    html += `<p>${esc(c.paras[i])}</p>`;
    if (cn[i] && cn[i].trim()) html += `<p class="tr">${esc(cn[i])}</p>`;
  }
  ta.innerHTML = html;
}

/* ---------- 实时翻译 ---------- */
const txKey = () => state.book ? (state.book.id + ':' + state.ci) : '';

function paintTx(total, filled) {
  const bar = $('#txbar');
  if (!bar) return;
  const c = state.ch;
  if (!c || !state.book || state.cn === 'en') { bar.hidden = true; return; }
  const cn = c.cn || [];
  total = total != null ? total : c.paras.filter(p => p.trim()).length;
  filled = filled != null ? filled : cn.filter(p => p && p.trim()).length;
  const tx = state.tx;

  if (tx && tx.err) {
    bar.hidden = false;
    bar.className = 'txbar err';
    bar.innerHTML = `<span class="tk">${txWord()}中断</span>
      <span class="tmsg">${esc(tx.err)}</span>
      <button id="txRetry">重试</button>`;
    $('#txRetry').onclick = () => startTranslate();
    return;
  }

  if (tx && tx.active) {
    bar.hidden = false;
    bar.className = 'txbar';
    const pct = tx.total ? Math.round(tx.done / tx.total * 100) : 0;
    const step = tx.total ? `${tx.done}/${tx.total} 块` : '准备中';
    bar.innerHTML = `<span class="tk">AI 实时${txWord()}</span>
      <span class="tmsg">${step} · 已${txWord()} ${filled}/${total} 段${
        tx.model ? ' · ' + esc(tx.model) : ''}</span>
      <span class="tprog ${tx.total ? '' : 'ind'}"><i style="width:${pct}%"></i></span>
      <button id="txStop">停止</button>`;
    $('#txStop').onclick = () => {
      state.stopped = txKey();
      if (tx.ctrl) tx.ctrl.abort();
    };
    return;
  }

  if (filled === 0) {
    if (state.stopped === txKey()) {
      bar.hidden = false;
      bar.className = 'txbar';
      bar.innerHTML = `<span class="tk">已停止</span>
        <span class="tmsg">本章尚未${txWord()}</span>
        <button id="txGo">继续${txWord()}</button>`;
      $('#txGo').onclick = () => { state.stopped = null; startTranslate(); };
      return;
    }
    if (!state.tr) { bar.hidden = true; return; }
    startTranslate();
    return;
  }

  if (filled < total) {
    bar.hidden = false;
    bar.className = 'txbar';
    bar.innerHTML = `<span class="tk">部分已${txWord()}</span>
      <span class="tmsg">${filled}/${total} 段，可继续${txWord()}剩余部分</span>
      <button id="txGo">续${txWord()}</button>`;
    $('#txGo').onclick = () => startTranslate();
    return;
  }

  bar.hidden = true;
}

async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (; ;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let ev;
        try { ev = JSON.parse(raw); } catch (e) { continue; }
        onEvent(ev);
      }
    }
  }
}

async function startTranslate() {
  if (!state.book || !state.tr) return;
  const id = state.book.id, idx = state.ci, key = id + ':' + idx;
  if (state.tx && state.tx.key === key && state.tx.active) return;
  if (state.tx && state.tx.ctrl) { try { state.tx.ctrl.abort(); } catch (e) { } }

  const ctrl = new AbortController();
  state.tx = { key, active: true, done: 0, total: 0, err: '', model: '', ctrl };
  paintTx();

  try {
    const res = await fetch(`/api/book/${id}/ch/${idx}/translate`, {
      method: 'POST', signal: ctrl.signal,
    });
    if (!res.ok) {
      let msg = 'HTTP ' + res.status;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) { }
      throw new Error(msg);
    }

    await readSSE(res, (ev) => {
      if (!state.tx || state.tx.key !== key) return;
      if (ev.t === 'meta') {
        state.tx.total = ev.blocks || 0;
        state.tx.model = ev.model || '';
      } else if (ev.t === 'prog') {
        state.tx.done = ev.done || 0;
        state.tx.total = ev.total || state.tx.total;
      } else if (ev.t === 'part') {
        const st = $('.paper').scrollTop;
        state.ch.cn = ev.cn || [];
        if (ev.cnTitle) state.ch.cnTitle = ev.cnTitle;
        state.tx.done = ev.done || 0;
        state.tx.total = ev.total || state.tx.total;
        renderChapter();
        $('.paper').scrollTop = st;
        return;
      } else if (ev.t === 'done') {
        state.ch.cn = ev.cn || [];
        if (ev.cnTitle) state.ch.cnTitle = ev.cnTitle;
        state.tx.active = false;
        const t = state.toc[idx];
        if (t && ev.cnTitle && !t.ct) t.ct = ev.cnTitle;
        const card = state.all.find(x => x.id === id);
        if (card) card.has_cn = true;
        state.book.has_cn = true;
        renderToc();
        renderChapter();
        return;
      } else if (ev.t === 'err') {
        throw new Error(ev.msg || (txWord() + '失败'));
      }
      paintTx();
    });

    if (state.tx && state.tx.key === key) {
      state.tx.active = false;
      paintTx();
    }
  } catch (e) {
    if (!state.tx || state.tx.key !== key) return;
    if (e && e.name === 'AbortError') { state.tx = null; paintTx(); return; }
    state.tx.active = false;
    state.tx.err = String((e && e.message) || e);
    paintTx();
  }
}

function closeReader() {
  if (state.tx && state.tx.ctrl) { try { state.tx.ctrl.abort(); } catch (e) { } }
  state.tx = null;
  $('#reader').hidden = true;
  $('#shelf').style.display = '';
  document.body.style.overflow = '';
  state.book = null;
  renderRecent();
}

/* ---------- 配置 ---------- */
function applyFont() {
  const def = window.innerWidth <= 560 ? 17 : 20;
  const fs = localStorage.getItem('md:fs') || def;
  document.documentElement.style.setProperty('--fs', fs + 'px');
}
function applyTheme() {
  const t = localStorage.getItem('md:theme') || 'day';
  document.documentElement.dataset.theme = t;
  const b = $('#themeBtn');
  if (b) b.textContent = t === 'night' ? '日间' : '夜间';
}

/* ---------- 事件 ---------- */
$('#q').addEventListener('input', e => { state.q = e.target.value; render(); });
$('#cats').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  state.cat = b.dataset.cat;
  [...$('#cats').children].forEach(x => x.classList.toggle('on', x === b));
  render();
});
$('#sort').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  state.sort = b.dataset.sort;
  [...$('#sort').children].forEach(x => x.classList.toggle('on', x === b));
  render();
});
$('#grid').addEventListener('click', e => {
  const c = e.target.closest('.card');
  if (c) openBook(c.dataset.id);
});
$('#recentList').addEventListener('click', e => {
  const c = e.target.closest('.rc');
  if (c) openBook(c.dataset.id);
});
$('#brand').addEventListener('click', closeReader);
$('#back').addEventListener('click', closeReader);
$('#tocList').addEventListener('click', e => {
  const a = e.target.closest('a');
  if (!a) return;
  e.preventDefault();
  loadChapter(+a.dataset.i);
  if (window.innerWidth <= 860) $('#toc').classList.remove('open');
});
$('#prevCh').addEventListener('click', () => state.ci > 0 && loadChapter(state.ci - 1));
$('#nextCh').addEventListener('click', () => state.ci < state.toc.length - 1 && loadChapter(state.ci + 1));
$('#tocBtn').addEventListener('click', () => $('#toc').classList.toggle('open'));
$('#fontMinus').addEventListener('click', () => {
  let fs = +localStorage.getItem('md:fs') || (window.innerWidth <= 560 ? 17 : 20);
  localStorage.setItem('md:fs', Math.max(14, fs - 1)); applyFont(); syncState();
});
$('#fontPlus').addEventListener('click', () => {
  let fs = +localStorage.getItem('md:fs') || (window.innerWidth <= 560 ? 17 : 20);
  localStorage.setItem('md:fs', Math.min(30, fs + 1)); applyFont(); syncState();
});
$('#themeBtn').addEventListener('click', () => {
  const t = localStorage.getItem('md:theme') === 'night' ? 'day' : 'night';
  localStorage.setItem('md:theme', t); applyTheme();
  $('#themeBtn').textContent = t === 'night' ? '日间' : '夜间';
  syncState();
});
$('#cnModes').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  state.cn = b.dataset.cn;
  if (state.cn === 'en' && state.tx) {
    if (state.tx.ctrl) { try { state.tx.ctrl.abort(); } catch (err) { } }
    state.tx = null;
  }
  const cm = lsGet('md:cn', {}) || {};
  cm[state.book.id] = state.cn;
  lsSet('md:cn', cm);
  syncState();
  [...$('#cnModes').children].forEach(x => x.classList.toggle('on', x === b));
  renderToc();
  renderChapter();
});

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault(); $('#q').focus(); return;
  }
  if (!$('#reader').hidden) {
    if (e.key === 'ArrowLeft' && state.ci > 0) loadChapter(state.ci - 1);
    if (e.key === 'ArrowRight' && state.ci < state.toc.length - 1) loadChapter(state.ci + 1);
    if (e.key === 'Escape') closeReader();
  }
});

/* ---------- 启动 ---------- */
(async function init() {
  applyFont(); applyTheme();
  const [lib, st, sv] = await Promise.all([api('/api/library'), api('/api/stats'), syncStateLoad()]);
  state.all = lib.items;
  if (sv && sv.prefs) {
    if (!localStorage.getItem('md:theme') && sv.prefs.theme) localStorage.setItem('md:theme', sv.prefs.theme);
    if (!localStorage.getItem('md:fs') && sv.prefs.fs) localStorage.setItem('md:fs', sv.prefs.fs);
    applyFont(); applyTheme();
  }
  $('#meta').textContent = `${st.books} 本 · ${(st.chars / 10000).toFixed(0)} 万字 · ${st.western} 种西典`;
  renderCats(st);
  render();
  renderRecent();
})();
