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
  hidden: false,
};

function fmtChars(n) {
  if (n >= 10000) return (n / 10000).toFixed(n >= 100000 ? 0 : 1) + ' 万字';
  return n + ' 字';
}
const UNIT = { '回': '回', '章': '章', '卷': '卷', '篇': '篇', '节': '节', '单': '节' };

function bookSize(b) {
  if (b.type === 'image') return b.n + ' 页';
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
      ${b.type === 'image' ? '<span class="comic">漫</span>' : ''}
      <div class="t">${esc(b.title)}</div>
      <div class="a">${esc(authorName(b.author))}</div>
      <div class="s">${b.source === 'user' ? '<span class="imp">导入</span> · ' : ''}<span class="c">${esc(b.cat)}</span>${b.has_cn ? `<span class="hascn">${b.lang === 'zh' ? '有白话' : '有译本'}</span> · ` : ''}${b.type === 'image' ? `${b.n} 页` : `${bookSize(b)} · ${b.n} ${UNIT[b.kind] || '节'}`}</div>
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

/* ---------- 会话状态：只存在内存里，不写 localStorage / cookie ---------- */
// 本版不采集任何用户信息：没有设备号、没有账号、没有埋点，
// 阅读进度与最近在读只在当前页面会话内有效，刷新即归零。
const mem = {
  theme: (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'night' : 'day',
  fs: 0,
  recent: [],
  pos: {},
  cn: {},
};

/* 清掉旧版本留在浏览器里的键（旧版本用 md: 前缀存过设备号与进度） */
try {
  Object.keys(localStorage).filter(k => k.indexOf('md:') === 0).forEach(k => localStorage.removeItem(k));
} catch (e) { }

const getPos = (id) => mem.pos[id] || 0;
const setPos = (id, i) => { mem.pos[id] = i; };

/* ---------- 最近在读（会话内） ---------- */
function renderRecent() {
  const list = mem.recent.filter(x => state.all.some(b => b.id === x.id)).slice(0, 6);
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
  mem.recent = [{ id, ci }].concat(mem.recent.filter(x => x.id !== id)).slice(0, 8);
}

/* ---------- 阅读器 ---------- */

async function openBook(id, resume = true) {
  try {
    const meta = await api('/api/book/' + id);
    state.book = meta;
    state.toc = meta.toc;
    state.tr = !!meta.translate;
    $('#btitle').textContent = meta.title;
    $('#delBtn').hidden = !id.startsWith('u');
    const isEn = meta.lang === 'en';
    const isImg = meta.type === 'image';
    $('#text').classList.toggle('imgs', isImg);
    $('.paper').classList.toggle('imgmode', isImg);
    $('#fontMinus').hidden = isImg;
    $('#fontPlus').hidden = isImg;
    let tag = '';
    if (isImg) {
      tag = ` · 漫画 · ${meta.toc.length} 页`;
    } else if (isEn) {
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
    state.cn = (!canCn) ? 'en' : (mem.cn[id] || 'en');
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
  stopScroll();
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

  if (state.book && state.book.type === 'image') {
    $('#ctitle').textContent = c.title;
    $('#txbar').hidden = true;
    const src = '/media/' + state.book.id + '/' + encodeURIComponent(c.img || '');
    const dim = c.w ? ` width="${c.w}" height="${c.h}"` : '';
    ta.innerHTML = c.img
      ? `<img class="pg" src="${src}"${dim} alt="${esc(c.title)}" decoding="async">`
      : '<p class="loading">这一页缺图</p>';
    preloadPage(state.ci + 1);
    return;
  }
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

function preloadPage(i) {
  if (!state.book || state.book.type !== 'image') return;
  if (i < 0 || i >= state.toc.length) return;
  const fn = String(i + 1).padStart(4, '0') + '.jpg';
  const im = new Image();
  im.src = '/media/' + state.book.id + '/' + fn;
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
  const fs = mem.fs || def;
  document.documentElement.style.setProperty('--fs', fs + 'px');
}
function applyTheme() {
  const t = mem.theme;
  document.documentElement.dataset.theme = t;
  const b = $('#themeBtn');
  if (b) b.textContent = t === 'night' ? '日间' : '夜间';
}

/* ---------- 事件 ---------- */
$('#q').addEventListener('input', e => { state.q = e.target.value; render(); });

/* ---------- 隐藏书柜：暗号在搜索框里输入，界面不留入口 ---------- */
let hideKey = '';
let hideBusy = false;

async function checkKey(v) {
  try {
    const r = await fetch('/api/hidden/check?key=' + encodeURIComponent(v));
    if (!r.ok) return false;
    return !!(await r.json()).ok;
  } catch (e) { return false; }
}

async function enterHidden(key) {
  if (hideBusy) return;
  hideBusy = true;
  hideKey = key;
  state.hidden = true;
  state.q = '';
  state.cat = '';
  $('#q').value = '';
  try {
    await loadShelf(true);
  } catch (e) {
    state.hidden = false;
    hideKey = '';
    hideBusy = false;
    alert('无法进入隐藏书柜：' + e);
    return;
  }
  $('#hbanner').hidden = false;
  $('#hero').hidden = true;
  $('#q').placeholder = '隐藏书柜内搜索';
  document.body.classList.add('hid');
  hideBusy = false;
}

async function exitHidden() {
  state.hidden = false;
  hideKey = '';
  state.q = '';
  state.cat = '';
  $('#q').value = '';
  $('#q').placeholder = '搜书名、作者';
  $('#hbanner').hidden = true;
  $('#hero').hidden = false;
  document.body.classList.remove('hid');
  await loadShelf(false);
}

$('#q').addEventListener('keydown', async e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim();
  if (!v) { if (state.hidden) { e.preventDefault(); await exitHidden(); } return; }
  if (await checkKey(v)) {
    e.preventDefault();
    if (state.hidden) await exitHidden(); else await enterHidden(v);
  }
});

$('#hbExit').addEventListener('click', exitHidden);
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
  const base = mem.fs || (window.innerWidth <= 560 ? 17 : 20);
  mem.fs = Math.max(14, base - 1); applyFont();
});
$('#fontPlus').addEventListener('click', () => {
  const base = mem.fs || (window.innerWidth <= 560 ? 17 : 20);
  mem.fs = Math.min(30, base + 1); applyFont();
});
$('#themeBtn').addEventListener('click', () => {
  mem.theme = mem.theme === 'night' ? 'day' : 'night';
  applyTheme();
});
$('#cnModes').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  state.cn = b.dataset.cn;
  if (state.cn === 'en' && state.tx) {
    if (state.tx.ctrl) { try { state.tx.ctrl.abort(); } catch (err) { } }
    state.tx = null;
  }
  mem.cn[state.book.id] = state.cn;
  [...$('#cnModes').children].forEach(x => x.classList.toggle('on', x === b));
  renderToc();
  renderChapter();
});

/* ---------- 匀速滚动：按住持续，轻点也走一小段 ---------- */
const held = { up: false, down: false };
const sc = { raf: 0, dir: 0, vel: 380, last: 0, until: 0 };

function scrollStart(dir) {
  const paper = document.querySelector('.paper');
  if (!paper) return;
  sc.dir = dir;
  sc.until = performance.now() + 200;   // 轻点一下也滑 200ms
  if (sc.raf) return;
  paper.style.scrollBehavior = 'auto';  // 关掉 CSS 平滑，改为逐帧匀速
  sc.last = performance.now();
  sc.raf = requestAnimationFrame(scrollTick);
}

function scrollTick(t) {
  const paper = document.querySelector('.paper');
  if (!paper) { sc.raf = 0; sc.dir = 0; return; }
  const dt = Math.min(0.06, Math.max(0, (t - sc.last) / 1000));
  sc.last = t;
  if (sc.dir) paper.scrollTop += sc.dir * sc.vel * dt;
  const holding = sc.dir < 0 ? held.up : held.down;
  if (holding || t < sc.until) {
    sc.raf = requestAnimationFrame(scrollTick);
  } else {
    sc.raf = 0;
    sc.dir = 0;
    paper.style.scrollBehavior = '';
  }
}

function stopScroll() {
  held.up = held.down = false;
  sc.dir = 0;
  if (sc.raf) { cancelAnimationFrame(sc.raf); sc.raf = 0; }
  const paper = document.querySelector('.paper');
  if (paper) paper.style.scrollBehavior = '';
}

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault(); $('#q').focus(); return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  // 导入弹窗打开时，Esc 直接关掉（输入框里也生效）
  if (!$('#impModal').hidden) {
    if (e.key === 'Escape') { closeImp(); e.preventDefault(); }
    return;
  }

  const el = e.target;
  const typing = !!(el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA'
    || el.tagName === 'SELECT' || el.isContentEditable));
  if ($('#reader').hidden || !$('#impModal').hidden || typing) {
    if (!$('#reader').hidden && $('#impModal').hidden && !typing && e.key === 'Escape') closeReader();
    return;
  }

  /* 阅读器内：W/S 匀速上下滚动，A/D 切换上一章 / 下一章（方向键等价） */
  const ch = (d) => {
    const n = state.ci + d;
    if (n >= 0 && n < state.toc.length) { loadChapter(n); e.preventDefault(); }
  };

  switch (e.code) {
    case 'KeyW': case 'ArrowUp': held.up = true; scrollStart(-1); e.preventDefault(); break;
    case 'KeyS': case 'ArrowDown': held.down = true; scrollStart(1); e.preventDefault(); break;
    case 'KeyA': case 'ArrowLeft': ch(-1); break;
    case 'KeyD': case 'ArrowRight': ch(1); break;
    case 'Escape': closeReader(); break;
    default: break;
  }
});

document.addEventListener('keyup', e => {
  if (e.code === 'KeyW' || e.code === 'ArrowUp') held.up = false;
  if (e.code === 'KeyS' || e.code === 'ArrowDown') held.down = false;
});
window.addEventListener('blur', stopScroll);

/* ---------- 触屏：左右轻扫切换章节 ---------- */
(() => {
  const paper = document.querySelector('.paper');
  if (!paper) return;
  let sx = 0, sy = 0, st = 0;
  paper.addEventListener('touchstart', e => {
    if (e.touches.length !== 1) return;
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
    st = Date.now();
  }, { passive: true });
  paper.addEventListener('touchend', e => {
    const t = e.changedTouches[0];
    if (!t || Date.now() - st > 700) return;
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;          // 正在选字，不翻章
    const dx = t.clientX - sx, dy = t.clientY - sy;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 1.8) return;
    const n = state.ci + (dx < 0 ? 1 : -1);
    if (n >= 0 && n < state.toc.length) loadChapter(n);
  }, { passive: true });
})();

/* ---------- 启动 ---------- */
async function loadShelf(hidden) {
  const h = hidden === undefined ? state.hidden : hidden;
  const qs = h ? '?hidden=1' : '';
  const opt = h ? { headers: { 'X-Hidden-Key': hideKey } } : {};
  const get = (u) => fetch(u, opt).then(r => r.ok ? r.json() : Promise.reject(r.status));
  const [lib, st] = await Promise.all([get('/api/library' + qs), get('/api/stats' + qs)]);
  state.all = lib.items;
  if (h) {
    $('#meta').textContent = `隐藏书柜 · ${st.books} 本`;
    $('#hbInfo').textContent = `隐藏书柜 · ${st.books} 本 · 不会出现在公开书架 · 搜索框再输一次暗号可退出`;
  } else {
    $('#meta').textContent = `${st.books} 本 · ${(st.chars / 10000).toFixed(0)} 万字 · ${st.western} 种西典`;
  }
  renderCats(st);
  render();
  renderRecent();
}

(async function init() {
  applyFont(); applyTheme();
  await loadShelf();
})();


/* ---------- 导入书籍 ---------- */
const imp = { text: '', busy: false, mode: '', tab: 'text', images: [], urls: [], resumeId: '' };

function impMsg(text, kind) {
  const el = $('#impMsg');
  el.textContent = text || '';
  el.className = 'impmsg' + (kind ? ' ' + kind : '');
}

function openImp() {
  const row = $('#impHiddenRow');
  row.hidden = !state.hidden;
  $('#impHidden').checked = !!state.hidden;
  setTab(imp.tab);
  $('#impModal').hidden = false;
  setTimeout(() => $('#impTitle').focus(), 40);
}

function closeImp() {
  if (imp.busy) return;
  $('#impModal').hidden = true;
  imp.text = '';
  imp.mode = '';
  imp.resumeId = '';
  clearImages();
  $('#impFile').value = '';
  $('#impTitle').value = '';
  $('#impAuthor').value = '';
  const ta = $('#impText');
  ta.value = '';
  ta.readOnly = false;
  ta.classList.remove('ro');
  $('#impFname').hidden = true;
  $('#impFname').textContent = '';
  impMsg('');
}

/* 已选文件信息行：文件名 + 字数 + 清除 */
function setFileInfo(name, chars) {
  const el = $('#impFname');
  el.textContent = '';
  const sp = document.createElement('span');
  sp.textContent = `${name} · ${chars.toLocaleString()} 字`;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = '清除';
  btn.addEventListener('click', e => { e.stopPropagation(); clearFile(); });
  el.append(sp, btn);
  el.hidden = false;
}

function clearFile() {
  imp.text = '';
  imp.mode = '';
  $('#impFile').value = '';
  $('#impFname').hidden = true;
  $('#impFname').textContent = '';
  const ta = $('#impText');
  if (ta.readOnly) {
    ta.readOnly = false;
    ta.value = '';
    ta.classList.remove('ro');
  }
  impMsg('已清除文件，可直接粘贴正文', '');
}

async function takeFile(f) {
  if (!f) return;
  if (f.size > 20 * 1024 * 1024) { impMsg('文件超过 20 MB，请先拆分', 'err'); return; }
  const buf = await f.arrayBuffer();
  let t = new TextDecoder('utf-8').decode(buf);
  if ((t.match(/\uFFFD/g) || []).length > 3) {
    try { t = new TextDecoder('gb18030').decode(buf); } catch (e) { }
  }
  imp.text = t;
  imp.mode = 'file';
  if (!$('#impTitle').value.trim()) {
    $('#impTitle').value = f.name.replace(/\.[^.]+$/, '').slice(0, 120);
  }
  // 只把开头一段放进文本框做预览，其余留在内存里，长文不会把弹窗撑开
  const ta = $('#impText');
  ta.value = t.slice(0, 600) + (t.length > 600 ? '\n…' : '');
  ta.readOnly = true;
  ta.classList.add('ro');
  setFileInfo(f.name, t.length);
  impMsg('已读取，点「导入并阅读」入库（文本框内为前 600 字预览）', 'ok');
}

async function doImport(opts) {
  if (imp.busy) return;
  opts = opts || {};
  // 选过文件就以文件为准，文本框里只是预览，避免被截断
  const text = (imp.mode === 'file' && imp.text ? imp.text : ($('#impText').value || '')).trim();
  if (text.length < 200) { impMsg('正文太短，至少 200 字', 'err'); return; }
  if (text.length > 6000000) { impMsg('正文超过 600 万字，请先拆分', 'err'); return; }
  imp.busy = true;
  $('#impGo').disabled = true;
  impMsg(opts.replace ? '正在用新内容更新旧书…' : '正在切章入库，大文件需要几秒…');
  try {
    const payload = {
      title: $('#impTitle').value.trim(),
      author: $('#impAuthor').value.trim(),
      cat: $('#impCat').value,
      text,
      hidden: !!$('#impHidden').checked,
    };
    if (opts.replace) payload.replace = opts.replace;
    if (opts.allowDuplicate) payload.allow_duplicate = true;

    const r = await fetch('/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await r.json().catch(() => ({}));

    // 同名书：让用户自己决定「覆盖」还是「另存」
    if (r.status === 409 && !opts.replace && !opts.allowDuplicate) {
      const d = (j.detail && j.detail.conflict) ? j.detail.conflict : {};
      const name = d.title || payload.title || '同名书籍';
      const yes = confirm(
        `已存在同名书籍《${name}》${d.n ? '（' + d.n + ' 节）' : ''}。\n\n` +
        '确定：用新内容更新它，章节标题与段落数对得上的旧译文会保留；\n' +
        '取消：另存为一本新书，旧书保持不动。'
      );
      imp.busy = false;
      $('#impGo').disabled = false;
      if (yes) { await doImport({ replace: d.id || '' }); }
      else { await doImport({ allowDuplicate: true }); }
      return;
    }

    if (!r.ok) {
      const msg = typeof j.detail === 'string' ? j.detail : (j.detail && j.detail.msg) || ('导入失败 ' + r.status);
      throw new Error(msg);
    }

    let note = (j.updated ? '已更新：' : '已入库：') + j.title + ' · ' + j.n + ' 节';
    if (j.updated) note += ' · 保留译文 ' + (j.kept_chapters || 0) + ' 章';
    impMsg(note, 'ok');
    imp.busy = false;
    $('#impGo').disabled = false;
    closeImp();
    await loadShelf(state.hidden);
    openBook(j.id, false);
  } catch (e) {
    imp.busy = false;
    $('#impGo').disabled = false;
    impMsg(String(e.message || e), 'err');
  }
}

/* ---------- 导入：图片 / 漫画 ---------- */
function setTab(t) {
  imp.tab = t === 'image' ? 'image' : 'text';
  [...$('#impTabs').children].forEach(x => x.classList.toggle('on', x.dataset.tab === imp.tab));
  $('#impTextPane').hidden = imp.tab !== 'text';
  $('#impImgPane').hidden = imp.tab !== 'image';
  $('#impGo').textContent = imp.tab === 'image' ? '上传并阅读' : '导入并阅读';
  $('#impTitle').placeholder = imp.tab === 'image' ? '留空则自动命名' : '留空则用文件名';
  impMsg('');
}

/* 文件名自然排序：1、2、10 而不是 1、10、2 */
function natKey(name) {
  return String(name || '').split(/(\d+)/)
    .map(x => (/^\d+$/.test(x) ? x.padStart(9, '0') : x.toLowerCase())).join('');
}

function clearImages() {
  imp.images = [];
  imp.urls.forEach(u => URL.revokeObjectURL(u));
  imp.urls = [];
  const pv = $('#imgPrev');
  if (pv) pv.innerHTML = '';
  const info = $('#imgInfo');
  if (info) { info.hidden = true; info.textContent = ''; }
}

function renderImages() {
  const list = imp.images;
  const pv = $('#imgPrev');
  pv.innerHTML = '';
  imp.urls.forEach(u => URL.revokeObjectURL(u));
  imp.urls = [];
  const show = list.slice(0, 6);
  show.forEach(f => {
    const u = URL.createObjectURL(f);
    imp.urls.push(u);
    const img = new Image();
    img.src = u;
    img.alt = f.name;
    pv.appendChild(img);
  });
  if (list.length > show.length) {
    const d = document.createElement('div');
    d.className = 'more';
    d.textContent = `+${list.length - show.length} 张`;
    pv.appendChild(d);
  }
  const bytes = list.reduce((a, f) => a + f.size, 0);
  const mb = (bytes / 1048576).toFixed(bytes >= 10485760 ? 0 : 1);
  const el = $('#imgInfo');
  el.textContent = `共 ${list.length} 页 · ${mb} MB`;
  el.hidden = false;
}

function takeImages(files, from) {
  imp.resumeId = '';   // 重新选图就从头算，避免和上次的半本混在一起
  const arr = [...(files || [])].filter(f =>
    /^image\//.test(f.type) || /\.(jpe?g|png|webp|gif|bmp|avif)$/i.test(f.name));
  if (!arr.length) { impMsg('没有可用的图片（jpg / png / webp / gif）', 'err'); return; }

  const seen = new Set(imp.images.map(f => f.name + ':' + f.size));
  const merged = imp.images.slice();
  arr.forEach(f => {
    const k = f.name + ':' + f.size;
    if (!seen.has(k)) { seen.add(k); merged.push(f); }
  });
  const path = f => f.webkitRelativePath || f.name;
  merged.sort((a, b) => natKey(path(a)).localeCompare(natKey(path(b))));

  let cut = false;
  if (merged.length > 400) { merged.length = 400; cut = true; }
  imp.images = merged;

  // 选文件夹时用目录名当书名；只选一张时用文件名。
  // 粘贴进来的图没有像样的名字，不拿它当书名。
  const first = arr[0].webkitRelativePath || '';
  if (from !== 'paste' && !$('#impTitle').value.trim()) {
    if (first.includes('/')) $('#impTitle').value = first.split('/')[0].slice(0, 120);
    else if (arr.length === 1) $('#impTitle').value = arr[0].name.replace(/\.[^.]+$/, '').slice(0, 120);
  }

  renderImages();
  const pre = from === 'paste' ? '已粘贴' : '已选';
  impMsg(cut ? '单本上限 400 页，超出部分已忽略' : `${pre} ${merged.length} 页，点「上传并阅读」入库`, cut ? 'err' : 'ok');
}

/* 带上传进度的 POST；fetch 拿不到上传进度，所以这里用 XHR */
function xhrUpload(url, fd, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', url);
    x.upload.onprogress = ev => {
      if (ev.lengthComputable) onProgress(Math.round(ev.loaded / ev.total * 100));
    };
    x.onload = () => {
      let j = {};
      try { j = JSON.parse(x.responseText || '{}'); } catch (e) { }
      if (x.status >= 200 && x.status < 300) return resolve(j);
      const d = j.detail;
      const msg = typeof d === 'string' ? d : (d && d.msg) || ('上传失败 ' + x.status);
      const err = new Error(msg);
      err.status = x.status;
      err.body = j;
      reject(err);
    };
    x.onerror = () => reject(new Error('网络中断，请重试'));
    x.send(fd);
  });
}

async function doImportImages(opts) {
  if (imp.busy) return;
  opts = opts || {};
  const files = imp.images;
  if (!files.length) { impMsg('请先选择图片', 'err'); return; }
  const title = $('#impTitle').value.trim();   // 留空则服务端自动命名

  imp.busy = true;
  $('#impGo').disabled = true;
  const BATCH = 24;          // 每批 24 张，几百页也不会把网关拖到超时
  let id = imp.resumeId || '';   // 上次中断时就接着往这本书里补
  let added = 0;
  let skipped = 0;
  let sent = 0;

  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const fd = new FormData();
      chunk.forEach(f => fd.append('files', f, f.name));
      if (!id) {
        fd.append('title', title);
        fd.append('author', $('#impAuthor').value.trim());
        fd.append('cat', $('#impCat').value);
        if ($('#impHidden').checked) fd.append('hidden', '1');
        if (opts.replace) fd.append('replace', opts.replace);
        if (opts.duplicate) fd.append('allow_duplicate', '1');
      } else {
        fd.append('append', id);
      }

      const range = `${i + 1}–${i + chunk.length}`;
      impMsg(`正在处理第 ${range} 页 / 共 ${files.length} 页…`);
      const j = await xhrUpload('/api/import/images', fd, pct => {
        impMsg(`正在上传第 ${range} 页 / 共 ${files.length} 页 · ${pct}%`);
      });
      id = j.id || id;
      added += j.added || 0;
      skipped += j.skipped || 0;
      sent += chunk.length;
    }

    imp.resumeId = '';
    imp.busy = false;
    $('#impGo').disabled = false;
    closeImp();
    await loadShelf(state.hidden);
    openBook(id, false);
  } catch (e) {
    if (e.status === 409 && !opts.replace && !opts.duplicate) {
      const d = (e.body && e.body.detail && e.body.detail.conflict) || {};
      const yes = confirm(
        `已存在同名书籍《${d.title || title}》${d.n ? '（' + d.n + ' 页/节）' : ''}。\n\n` +
        '确定：用这批图片覆盖它，旧页会被清空；\n' +
        '取消：另存为一本新书。'
      );
      imp.busy = false;
      $('#impGo').disabled = false;
      if (yes) await doImportImages({ replace: d.id || '' });
      else await doImportImages({ duplicate: true });
      return;
    }
    imp.busy = false;
    $('#impGo').disabled = false;
    const extra = skipped ? `（${skipped} 页被跳过）` : '';

    // 已经建好书、只是后面几批失败：记住断点，下次只补剩下的页，避免重复
    if (id && sent < files.length) {
      imp.resumeId = id;
      imp.images = files.slice(sent);
      renderImages();
      $('#impGo').textContent = '继续上传';
      impMsg(`已传 ${sent} / ${files.length} 页，后面失败了：${e.message || e}${extra}。` +
             `点「继续上传」只补剩下的 ${files.length - sent} 页。`, 'err');
      return;
    }
    impMsg(String(e.message || e) + extra, 'err');
  }
}

$('#impTabs').addEventListener('click', e => {
  const b = e.target.closest('[data-tab]');
  if (b) setTab(b.dataset.tab);
});
$('#imgDrop').addEventListener('click', () => $('#imgFile').click());
$('#imgDrop').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#imgFile').click(); }
});
$('#imgPickDir').addEventListener('click', e => { e.stopPropagation(); $('#imgDir').click(); });
$('#imgFile').addEventListener('change', e => { takeImages(e.target.files); e.target.value = ''; });
$('#imgDir').addEventListener('change', e => { takeImages(e.target.files); e.target.value = ''; });
['dragenter', 'dragover'].forEach(t => $('#imgDrop').addEventListener(t, e => {
  e.preventDefault(); $('#imgDrop').classList.add('over');
}));
['dragleave', 'drop'].forEach(t => $('#imgDrop').addEventListener(t, e => {
  e.preventDefault(); $('#imgDrop').classList.remove('over');
}));
$('#imgDrop').addEventListener('drop', e => {
  const dt = e.dataTransfer;
  if (dt && dt.files && dt.files.length) takeImages(dt.files);
});

async function delBook() {
  const b = state.book;
  if (!b) return;
  const token = prompt('删除《' + b.title + '》需要管理口令（服务端 ADMIN_TOKEN）：');
  if (token == null) return;
  const r = await fetch('/api/book/' + b.id, {
    method: 'DELETE',
    headers: { 'X-Admin-Token': token },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { alert(j.detail || ('删除失败 ' + r.status)); return; }
  closeReader();
  await loadShelf(state.hidden);
}

$('#impBtn').addEventListener('click', openImp);
$('#impModal').addEventListener('click', e => {
  if (e.target.closest('[data-close]')) closeImp();
});
$('#impDrop').addEventListener('click', () => $('#impFile').click());
$('#impDrop').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#impFile').click(); }
});
$('#impFile').addEventListener('change', e => takeFile(e.target.files[0]));
['dragenter', 'dragover'].forEach(t => $('#impDrop').addEventListener(t, e => {
  e.preventDefault(); $('#impDrop').classList.add('over');
}));
['dragleave', 'drop'].forEach(t => $('#impDrop').addEventListener(t, e => {
  e.preventDefault(); $('#impDrop').classList.remove('over');
}));
$('#impDrop').addEventListener('drop', e => {
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) takeFile(f);
});

/* ---------- 粘贴导入：截图 / 复制的图片 / .txt·.md 文件，Ctrl+V 直接进弹窗 ---------- */
const CLIP_MIME = {
  jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp',
  gif: 'image/gif', bmp: 'image/bmp', avif: 'image/avif',
};

// 剪贴板里的图名多半是 image.png / blob，同名同尺寸会被 takeImages 的去重当成重复。
// 统一改名为 zz-paste-0001 起，既唯一，又排在已选图片之后（后粘的放最后）。
function clipImage(f, i, base) {
  const m = (f.name || '').match(/\.([a-z0-9]+)$/i);
  const ext = (m ? m[1] : (f.type.split('/')[1] || 'png')).toLowerCase()
    .replace('jpeg', 'jpg').replace('svg+xml', 'svg');
  const name = `zz-paste-${String(base + i + 1).padStart(4, '0')}.${ext}`;
  try { return new File([f], name, { type: f.type || CLIP_MIME[ext] || 'image/png' }); }
  catch (err) { return f; }   // 老浏览器不支持 File 构造，退回原名
}

document.addEventListener('paste', e => {
  const modal = $('#impModal');
  if (!modal || modal.hidden || imp.busy) return;
  const dt = e.clipboardData;
  if (!dt) return;

  // 1) 剪贴板里带文件：截图、网页上复制的图片、资源管理器里复制的文件
  const files = [];
  if (dt.files && dt.files.length) files.push(...dt.files);
  if (!files.length && dt.items) {
    for (const it of dt.items) {
      if (it.kind !== 'file') continue;
      const f = it.getAsFile();
      if (f) files.push(f);
    }
  }

  if (files.length) {
    const imgs = files.filter(f =>
      /^image\//.test(f.type) || /\.(jpe?g|png|webp|gif|bmp|avif)$/i.test(f.name || ''));
    if (imgs.length) {
      e.preventDefault();
      setTab('image');                       // 切到图片页，粘贴的图立刻能看到缩略图
      const base = imp.images.length;
      takeImages(imgs.map((f, i) => clipImage(f, i, base)), 'paste');
      return;
    }
    e.preventDefault();
    const txt = files.find(f => /^text\//.test(f.type) || /\.(txt|md|text)$/i.test(f.name || ''));
    if (txt) takeFile(txt);
    else impMsg('只能粘贴图片或 .txt / .md 文本文件', 'err');
    return;
  }

  // 2) 纯文本：贴在书名框里的长文明显放错了位置，改送进正文框
  const t = dt.getData('text/plain') || '';
  if (!t) return;
  const el = document.activeElement;
  if (el && el.id === 'impText') return;      // 正文框自己会处理，不抢
  if (t.length <= 120 && !t.includes('\n')) return;   // 短词多半是在填书名/作者，放行
  if (imp.tab !== 'text') return;            // 图片页不接管文本
  e.preventDefault();
  if (imp.mode === 'file') { impMsg('已选文件，先点「清除」再粘贴正文', 'err'); return; }
  const ta = $('#impText');
  const cur = ta.value.replace(/\s*$/, '');
  const total = (cur ? cur.length + 2 : 0) + t.length;
  if (total > 6000000) { impMsg('粘贴内容超过 600 万字，请存成文件后拖入', 'err'); return; }
  ta.value = (cur ? cur + '\n\n' : '') + t;
  impMsg(`已粘贴 ${t.length.toLocaleString()} 字，可继续粘贴，或点「导入并阅读」`, 'ok');
});
$('#impGo').addEventListener('click', () => (imp.tab === 'image' ? doImportImages() : doImport()));
$('#delBtn').addEventListener('click', delBook);
$('#impText').addEventListener('input', () => { if ($('#impText').value.trim()) impMsg(''); });
