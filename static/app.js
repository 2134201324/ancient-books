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
    $('#delBtn').hidden = false;   // 内置书与导入书都能删，口令在点击后校验
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
    if (scrollTop) jumpTo(0);
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

/* 立即定位：临时关掉 CSS 平滑，避免切章时从上一章的位置一路滑过去 */
function jumpTo(top) {
  const p = document.querySelector('.paper');
  if (!p) return;
  p.style.scrollBehavior = 'auto';
  p.scrollTop = top;
  requestAnimationFrame(() => { if (!sc.raf) p.style.scrollBehavior = ''; });
}

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

/* ---------- 点击左右边缘翻页：左边上一页，右边下一页 ---------- */
async function turnPage(dir) {
  if ($('#reader').hidden) return;
  const paper = document.querySelector('.paper');
  if (!paper || state.loading) return;
  stopScroll();

  // 图片书一页一屏，滚动没有意义，直接翻页
  if (state.book && state.book.type === 'image') {
    const n = state.ci + dir;
    if (n >= 0 && n < state.toc.length) await loadChapter(n);
    return;
  }

  const max = Math.max(0, paper.scrollHeight - paper.clientHeight);
  const step = Math.max(80, Math.round(paper.clientHeight * 0.86));   // 留一成重叠，不丢行
  const atTop = paper.scrollTop <= 2;
  const atEnd = paper.scrollTop >= max - 2;

  if (dir > 0) {
    if (atEnd || max === 0) {                       // 到底了，翻下一章
      if (state.ci < state.toc.length - 1) await loadChapter(state.ci + 1);
      return;
    }
  } else if (atTop) {                               // 到顶了，翻上一章并落到末尾
    if (state.ci > 0) {
      await loadChapter(state.ci - 1, false);
      const p = document.querySelector('.paper');
      if (p) jumpTo(p.scrollHeight);
    }
    return;
  }
  paper.scrollTop = Math.max(0, Math.min(max, paper.scrollTop + dir * step));
}

(() => {
  [[$('#flipPrev'), -1], [$('#flipNext'), 1]].forEach(([el, dir]) => {
    if (!el) return;
    let down = null;
    el.addEventListener('pointerdown', e => {
      down = (e.pointerType === 'mouse' && e.button !== 0)
        ? null : { x: e.clientX, y: e.clientY, t: Date.now() };
    });
    el.addEventListener('pointerup', e => {
      const d = down;
      down = null;
      if (!d) return;
      if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 12) return;  // 拖动 / 滑动，按误触忽略
      if (Date.now() - d.t > 900) return;                             // 长按不翻
      const s = window.getSelection();
      if (s && !s.isCollapsed) return;                                // 正在选字，不翻
      turnPage(dir);
    });
    el.addEventListener('pointercancel', () => { down = null; });
    el.addEventListener('contextmenu', e => e.preventDefault());
  });
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
/* 文本与图片共用一个导入面板：拖进来什么就建什么书，不必先选类型。
   imp.text 存文本文件正文，imp.images 存待上传的图片，两者可同时存在，
   提交时先建文本书、再建漫画书。 */
const imp = {
  text: '',        // 文本文件正文，'' 表示没选文件
  mode: '',        // '' | 'file'
  images: [],      // 待上传图片（含粘贴）
  urls: [],
  resumeId: '',    // 图片上传中断后的续传书号
  sort: 'name',    // name | time-asc | time-desc | manual
  dragFrom: -1,    // 正在拖动的缩略图序号
  chain: 0,        // 混合提交时的剩余任务数
  lastId: '',      // 混合提交里最后一本书的 id
  stageId: '',     // 覆盖更新的暂存会话；有值表示「新图已收在服务端，还没替换旧书」
  stageTarget: '', // 这次覆盖的是哪本书
  stageExpect: 0,  // 本次总共要传多少页
  sent: 0,         // 已成功上传的页数（从 images 头部算起），续传时从这里切片
};

/* 手机浏览器（iOS Safari / Android Chrome）不实现 webkitdirectory，
   点「整个文件夹」只会弹普通的文件选择，所以这个入口在手机上直接撤掉，
   换成说明 + ZIP（压缩包里带目录，解压后仍能还原顺序）。 */
const MOBILE = /Android|iPhone|iPad|iPod|Windows Phone|HarmonyOS/i.test(navigator.userAgent)
  || (navigator.maxTouchPoints > 1 && /Macintosh/.test(navigator.userAgent));
if (MOBILE) {
  const dw = $('#impDirWrap');
  if (dw) dw.remove();              // 连同它前面的分隔符一起拿掉，避免出现「/ /」
  const dh = $('#impDropHint');
  if (dh) dh.textContent = '手机不能选整个文件夹：可多选图片，页序用下方排序调整；打包成 ZIP 上传可保留目录顺序';
}

function impMsg(text, kind) {
  const el = $('#impMsg');
  el.textContent = text || '';
  el.className = 'impmsg' + (kind ? ' ' + kind : '');
}

function openImp() {
  const row = $('#impHiddenRow');
  row.hidden = !state.hidden;
  $('#impHidden').checked = !!state.hidden;
  $('#impModal').hidden = false;
  syncImp();
  setTimeout(() => $('#impTitle').focus(), 40);
}

function closeImp() {
  if (imp.busy) return;
  // 更新做到一半就关窗，先把话说清楚：旧书没动，但已传的页会作废
  if (imp.stageId) {
    const n = imp.stageExpect || 0;
    if (!confirm(`这次更新还没提交：新图已暂存 ${n} 页，旧书目前没有任何改动。\n\n` +
      '关闭后需要重新上传才能完成更新。确定关闭？')) return;
    dropStage();
  }
  $('#impModal').hidden = true;
  imp.text = '';
  imp.mode = '';
  imp.resumeId = '';
  imp.chain = 0;
  imp.sent = 0;
  clearImages();
  $('#impFile').value = '';
  $('#impDir').value = '';
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
  ta.readOnly = false;
  ta.value = '';
  ta.classList.remove('ro');
  syncImp();
  impMsg(stageHint(), '');
}

/* 根据当前暂存内容刷新面板：显隐、按钮文案、书名占位符 */
function stageHint() {
  const hasT = !!imp.text;
  const n = imp.images.length;
  if (hasT && n) return `文本 ${imp.text.length.toLocaleString()} 字 + 图片 ${n} 页，将分别入库 2 本（文字书 + 漫画书）`;
  if (hasT) return `已读取 ${imp.text.length.toLocaleString()} 字，点「导入并阅读」入库`;
  if (n) return `已选 ${n} 页，点「上传并阅读」入库`;
  return '';
}

function syncImp() {
  const hasT = !!imp.text;
  const n = imp.images.length;
  $('#impStage').hidden = n === 0;
  const ta = $('#impText');
  ta.hidden = n > 0;          // 有图时收起正文框，避免两块输入区互相干扰
  if (imp.stageId || imp.resumeId) {
    $('#impGo').textContent = (imp.stageId && imp.stageExpect && imp.sent >= imp.stageExpect)
      ? '再次提交' : '继续上传';
  } else {
    $('#impGo').textContent = hasT && n ? '导入 2 本' : (n ? '上传并阅读' : '导入并阅读');
  }
  $('#impTitle').placeholder = (n && !hasT) ? '留空则自动命名' : '留空则用文件名';
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
  syncImp();
  impMsg(stageHint(), 'ok');
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
        '确定：用新内容替换旧正文（不可撤销），章节标题与段落数对得上的旧译文会保留；\n' +
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
    if (await finishTask(j.id)) {
      impMsg(note, 'ok');
      await loadShelf(state.hidden);
      openBook(j.id, false);
    }
  } catch (e) {
    failTask(String(e.message || e));
  }
}

/* 一个任务做完：混合提交时接着做下一个，否则收尾开书 */
async function finishTask(id) {
  imp.lastId = id || imp.lastId;
  imp.chain = Math.max(0, imp.chain - 1);
  imp.busy = false;
  $('#impGo').disabled = false;
  if (imp.chain > 0) {      // 还有图片要传，弹窗留着
    impMsg('文字已入库，正在处理图片…');
    return false;
  }
  const last = imp.lastId;
  closeImp();
  if (last && last !== id) openBook(last, false);
  return true;
}

function failTask(msg) {
  imp.chain = 0;
  imp.busy = false;
  $('#impGo').disabled = false;
  impMsg(msg, 'err');
}

/* ---------- 导入：图片 / 漫画 ---------- */
/* 文件名自然排序：1、2、10 而不是 1、10、2 */
function natKey(name) {
  return String(name || '').split(/(\d+)/)
    .map(x => (/^\d+$/.test(x) ? x.padStart(9, '0') : x.toLowerCase())).join('');
}

/* 相对路径：选文件夹带 webkitRelativePath，拖文件夹由我们补 relPath */
const relPath = f => f.webkitRelativePath || f.relPath || f.name;

/* 按当前排序依据重排；manual 时保留数组顺序（拖动结果） */
function applySort() {
  const byName = (a, b) => natKey(relPath(a)).localeCompare(natKey(relPath(b)));
  if (imp.sort === 'time-asc') imp.images.sort((a, b) => (a.lastModified - b.lastModified) || byName(a, b));
  else if (imp.sort === 'time-desc') imp.images.sort((a, b) => (b.lastModified - a.lastModified) || byName(a, b));
  else if (imp.sort === 'name') imp.images.sort(byName);
}

function clearImages() {
  imp.images = [];
  imp.urls.forEach(u => URL.revokeObjectURL(u));
  imp.urls = [];
  const pv = $('#imgPrev');
  if (pv) pv.innerHTML = '';
  const sum = $('#impSummary');
  if (sum) sum.textContent = '';
}

/* 暂存区：每张图带页序、可拖动排序、可单独移除 */
function renderImages() {
  const list = imp.images;
  const pv = $('#imgPrev');
  pv.innerHTML = '';
  imp.urls.forEach(u => URL.revokeObjectURL(u));
  imp.urls = [];

  list.forEach((f, i) => {
    const u = URL.createObjectURL(f);
    imp.urls.push(u);

    const box = document.createElement('div');
    box.className = 'pgitem';
    box.draggable = true;
    box.dataset.i = i;
    box.title = relPath(f);

    const img = new Image();
    img.src = u;
    img.alt = relPath(f);
    box.appendChild(img);

    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = i + 1;
    box.appendChild(no);

    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'rm';
    x.textContent = '✕';
    x.title = '移除这一页';
    x.addEventListener('click', ev => { ev.stopPropagation(); dropImage(i); });
    box.appendChild(x);

    pv.appendChild(box);
  });

  const bytes = list.reduce((a, f) => a + f.size, 0);
  const mb = (bytes / 1048576).toFixed(bytes >= 10485760 ? 0 : 1);
  $('#impSummary').textContent = `共 ${list.length} 页 · ${mb} MB`;
  $('#imgHint').hidden = list.length < 2;
}

function moveImage(from, to) {
  if (from === to || from < 0 || to < 0 || from >= imp.images.length) return;
  const [f] = imp.images.splice(from, 1);
  imp.images.splice(to, 0, f);
  imp.sort = 'manual';               // 手动调过就以手序为准，不再被自动排序覆盖
  $('#impSort').value = 'manual';
  renderImages();
  impMsg(stageHint(), 'ok');
}

function dropImage(i) {
  imp.images.splice(i, 1);
  renderImages();
  syncImp();
  impMsg(stageHint() || '已移除，可继续选择或粘贴', '');
}

function takeImages(files, from) {
  if (from !== 'paste') {
    imp.resumeId = '';   // 重新选图就从头算，避免和上次的半本混在一起
    imp.sent = 0;
    dropStage();         // 重新选图也表示放弃上次没提交的更新
  }
  const arr = [...(files || [])].filter(f =>
    /^image\//.test(f.type) || /\.(jpe?g|png|webp|gif|bmp|avif)$/i.test(f.name));
  if (!arr.length) { impMsg('没有可用的图片（jpg / png / webp / gif）', 'err'); return; }

  const seen = new Set(imp.images.map(f => relPath(f) + ':' + f.size));
  arr.forEach(f => {
    const k = relPath(f) + ':' + f.size;
    if (!seen.has(k)) { seen.add(k); imp.images.push(f); }
  });

  applySort();

  let cut = false;
  if (imp.images.length > 400) { imp.images.length = 400; cut = true; }

  // 选文件夹时用目录名当书名；只选一张时用文件名。
  // 粘贴进来的图没有像样的名字，不拿它当书名。
  const first = relPath(arr[0]);
  if (from !== 'paste' && !imp.text && !$('#impTitle').value.trim()) {
    if (first.includes('/')) $('#impTitle').value = first.split('/')[0].slice(0, 120);
    else if (arr.length === 1) $('#impTitle').value = arr[0].name.replace(/\.[^.]+$/, '').slice(0, 120);
  }

  renderImages();
  syncImp();
  impMsg(cut ? '单本上限 400 页，超出部分已忽略' : stageHint(), cut ? 'err' : 'ok');
}

/* ---------- ZIP：在浏览器里就地解压，之后与「选文件夹」走同一条流程 ---------- */
const ZIP_MAX = 200 * 1024 * 1024;      // 压缩包上限（手机内存吃不消更大的）
const mimeOf = n => /\.png$/i.test(n) ? 'image/png'
  : /\.webp$/i.test(n) ? 'image/webp'
    : /\.gif$/i.test(n) ? 'image/gif'
      : /\.bmp$/i.test(n) ? 'image/bmp'
        : /\.avif$/i.test(n) ? 'image/avif' : 'image/jpeg';

/* 中文 ZIP 常用 GBK 且不置 UTF-8 标志位，先按 UTF-8 严格解，失败再退 GBK */
function zipName(bytes) {
  try { return new TextDecoder('utf-8', { fatal: true }).decode(bytes); } catch (e) { }
  try { return new TextDecoder('gbk').decode(bytes); } catch (e) { }
  return new TextDecoder('utf-8').decode(bytes);
}

async function inflateRaw(bytes) {
  const s = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(s).arrayBuffer());
}

/* 读中央目录取文件名 / 压缩方式 / 偏移，再按本地头定位数据段。
   只认 store(0) 与 deflate(8)，这两种覆盖了 99% 的压缩包。 */
async function unzipImages(file, onStep) {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error('这个浏览器不支持在线解压，请解压后直接选图片，或在电脑上导入');
  }
  const buf = new Uint8Array(await file.arrayBuffer());
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const u16 = o => dv.getUint16(o, true);
  const u32 = o => dv.getUint32(o, true);

  let eocd = -1;
  for (let i = buf.length - 22, stop = Math.max(0, buf.length - 66000); i >= stop; i--) {
    if (u32(i) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('不是有效的 ZIP 压缩包');

  const count = u16(eocd + 10);
  let off = u32(eocd + 16);
  const out = [];
  for (let n = 0; n < count; n++) {
    if (off + 46 > buf.length || u32(off) !== 0x02014b50) break;
    const method = u16(off + 10);
    const csize = u32(off + 20);
    const usize = u32(off + 24);
    const nlen = u16(off + 28), elen = u16(off + 30), clen = u16(off + 32);
    const lho = u32(off + 42);
    const name = zipName(buf.subarray(off + 46, off + 46 + nlen)).replace(/\\/g, '/');
    off += 46 + nlen + elen + clen;

    if (!/\.(jpe?g|png|webp|gif|bmp|avif)$/i.test(name)) continue;
    if (name.startsWith('__MACOSX/') || /(^|\/)\./.test(name)) continue;   // 系统垃圾与隐藏文件
    if (name.endsWith('/') || usize > 16 * 1024 * 1024) continue;
    if (lho + 30 > buf.length || u32(lho) !== 0x04034b50) continue;

    const start = lho + 30 + u16(lho + 26) + u16(lho + 28);
    const comp = buf.subarray(start, start + csize);
    let raw = null;
    try {
      if (method === 0) raw = comp;
      else if (method === 8) raw = await inflateRaw(comp);
    } catch (e) { raw = null; }
    if (!raw) continue;

    const base = name.split('/').pop();
    const f = new File([raw], base, { type: mimeOf(base), lastModified: file.lastModified });
    try { Object.defineProperty(f, 'relPath', { value: name, configurable: true }); } catch (e) { }
    out.push(f);
    if (onStep && out.length % 6 === 0) onStep(out.length);
    if (out.length >= 400) break;        // 单本上限，后面的一定也装不下
  }
  return out;
}

async function takeZip(f) {
  if (f.size > ZIP_MAX) {
    impMsg(`压缩包 ${(f.size / 1048576).toFixed(0)} MB 超过 200 MB 上限，请分批打包`, 'err');
    return;
  }
  imp.busy = true;
  $('#impGo').disabled = true;
  impMsg(`正在解压 ${f.name}…`);
  try {
    const files = await unzipImages(f, n => impMsg(`正在解压 ${f.name} · 已读出 ${n} 页…`));
    if (!files.length) throw new Error('压缩包里没有可用的图片（jpg / png / webp / gif / bmp / avif）');
    takeImages(files, 'zip');
    if (!$('#impTitle').value.trim()) {
      $('#impTitle').value = f.name.replace(/\.zip$/i, '').slice(0, 120);
    }
  } catch (e) {
    impMsg(String(e.message || e), 'err');
  } finally {
    imp.busy = false;
    $('#impGo').disabled = false;
  }
}

/* 统一入口：拖进来 / 选进来的东西按类型分流，文本进正文、图片进暂存区 */
async function takeFiles(files, opts) {
  opts = opts || {};
  const all = [...(files || [])];

  // 压缩包单独处理：里面本来就是一整批图，和别的文件混着传没有意义
  const zips = all.filter(f => /\.zip$/i.test(f.name) || /zip/i.test(f.type || ''));
  if (zips.length) {
    if (zips.length > 1) impMsg('一次只解压一个压缩包，已取第一个', '');
    await takeZip(zips[0]);
    const rest = all.length - zips.length;
    if (rest > 0) {
      const el = $('#impMsg');
      el.textContent = (el.textContent ? el.textContent + ' · ' : '') + `另有 ${rest} 个文件未处理，压缩包请单独上传`;
    }
    return;
  }

  // HEIC 浏览器解不了，服务端也没装解码器：先摘出来单独提示，别让它混进图片再失败
  const heic = all.filter(f => /\.(heic|heif)$/i.test(f.name));
  const rest = all.filter(f => !heic.includes(f));

  const imgs = rest.filter(f =>
    /^image\//.test(f.type) || /\.(jpe?g|png|webp|gif|bmp|avif)$/i.test(f.name));
  const txts = rest.filter(f =>
    !imgs.includes(f) && (/^text\//.test(f.type) || /\.(txt|md|text)$/i.test(f.name)));

  if (txts.length) {
    if (imp.text) impMsg('只接收一个文本文件，已用新的替换旧的', '');
    await takeFile(txts[0]);
    if (txts.length > 1) impMsg(`一次只导入一个文本文件，已取《${txts[0].name}》`, 'err');
  }

  if (imgs.length) takeImages(imgs, opts.from);

  const other = all.length - imgs.length - txts.length - heic.length;
  if (!imgs.length && !txts.length) {
    if (heic.length) impMsg(`${heic.length} 张 HEIC / HEIF 照片浏览器无法解码，请在相册里导出为 JPEG 后再传`, 'err');
    else impMsg(other ? '只能导入 .txt / .md 文本、图片，或图片打包成的 .zip' : '没有可导入的文件', 'err');
  } else {
    if (other > 0 && !imp.text) impMsg(`已忽略 ${other} 个不支持的文件`, '');
    if (heic.length) {
      const tip = `另有 ${heic.length} 张 HEIC 未导入，请先导出为 JPEG`;
      const el = $('#impMsg');
      el.textContent = (el.textContent ? el.textContent + ' · ' : '') + tip;
    }
  }
}

/* 拖拽：文件和文件夹一起接，文件夹递归展开 */
function readEntries(reader) {
  return new Promise((res, rej) => reader.readEntries(res, rej));
}

async function walkEntry(entry, prefix, out) {
  if (entry.isFile) {
    const f = await new Promise((res, rej) => entry.file(res, rej));
    try { Object.defineProperty(f, 'relPath', { value: prefix + f.name, configurable: true }); }
    catch (e) { }
    out.push(f);
    return;
  }
  if (!entry.isDirectory) return;
  const reader = entry.createReader();
  const dir = prefix + entry.name + '/';
  for (; ;) {
    const batch = await readEntries(reader);
    if (!batch.length) break;
    for (const e of batch) await walkEntry(e, dir, out);
  }
}

async function filesFromDrop(dt) {
  const entries = [];
  for (const it of (dt.items || [])) {
    if (it.kind !== 'file') continue;
    const e = it.webkitGetAsEntry && it.webkitGetAsEntry();
    if (e) entries.push(e);
  }
  if (entries.length) {
    const out = [];
    for (const e of entries) await walkEntry(e, '', out);
    if (out.length) return out;
  }
  return [...(dt.files || [])];
}

/* 带上传进度的 POST；fetch 拿不到上传进度，所以这里用 XHR */
function xhrUpload(url, fd, onProgress, opt) {
  opt = opt || {};
  const timeout = opt.timeout || 240000;
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', url);
    x.timeout = timeout;
    if (onProgress) {
      x.upload.onprogress = ev => {
        if (ev.lengthComputable) onProgress(Math.round(ev.loaded / ev.total * 100));
      };
    }
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
    x.onerror = () => reject(new Error('网络中断，请检查连接'));
    x.ontimeout = () => {
      const e = new Error(`超过 ${Math.round(timeout / 1000)} 秒没有回应`);
      e.timeout = true;
      reject(e);
    };
    x.send(fd);
  });
}

/* 同一批用同一个幂等令牌重试：服务端若已收下会直接回放结果，不会重复写页 */
async function uploadRetry(url, fd, onProgress, tries) {
  tries = tries || 3;
  let last;
  for (let k = 0; k < tries; k++) {
    try {
      return await xhrUpload(url, fd, onProgress);
    } catch (e) {
      last = e;
      const retriable = !e.status || e.status >= 500;   // 4xx 是内容问题，重试没意义
      if (!retriable || k === tries - 1) throw e;
      impMsg(`${e.message || e}，第 ${k + 1} 次重试…`);
      await new Promise(r => setTimeout(r, 900 * Math.pow(2, k)));
    }
  }
  throw last;
}

/* 丢弃未提交的暂存会话（服务端 24 小时也会自动回收，这里主动清一次） */
function dropStage() {
  if (!imp.stageId) return;
  const sid = imp.stageId;
  imp.stageId = '';
  imp.stageTarget = '';
  imp.stageExpect = 0;
  fetch('/api/import/images/stage/' + encodeURIComponent(sid), { method: 'DELETE' }).catch(() => { });
}

/* 提交中断后判断到底成没成：会话还在=没提交，会话没了且页数对得上=已经提交 */
async function stageVerdict(sid, target, total) {
  try {
    const r = await fetch('/api/import/images/stage/' + encodeURIComponent(sid));
    if (r.ok) return 'pending';
    if (r.status !== 404) return 'unknown';
  } catch (e) {
    return 'unknown';
  }
  try {
    const b = await fetch('/api/book/' + encodeURIComponent(target || sid)).then(x => x.json());
    const got = (b.toc || []).length;
    if (b.type === 'image' && got && (!total || got === total)) return 'committed';
  } catch (e) { }
  return 'unknown';
}

async function imageDone(id) {
  imp.busy = false;
  $('#impGo').disabled = false;
  imp.stageId = '';
  imp.stageTarget = '';
  imp.stageExpect = 0;
  imp.resumeId = '';
  imp.sent = 0;
  if (await finishTask(id)) {
    await loadShelf(state.hidden);
    openBook(id, false);
  }
}

async function doImportImages(opts) {
  if (imp.busy) return;
  opts = opts || {};
  const resuming = !!(imp.stageId || imp.resumeId);
  const files = resuming ? imp.images.slice(imp.sent || 0) : imp.images;
  if (!files.length && !imp.stageId) { impMsg('请先选择图片', 'err'); return; }
  // 混合提交时图片书不跟文字书抢同一个名字，留空让服务端自动命名
  const title = opts.titleOverride !== undefined ? opts.titleOverride : $('#impTitle').value.trim();
  const cover = opts.replace || imp.stageTarget || '';   // 要覆盖的书号，空=新建
  const total = imp.stageExpect || imp.images.length;    // 续传时沿用最初的总页数

  imp.busy = true;
  $('#impGo').disabled = true;
  if (cover && !imp.stageExpect) imp.stageExpect = total;

  const BATCH = 24;          // 每批 24 张，几百页也不会把网关拖到超时
  const runId = 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const base = imp.sent || 0;   // 续传起点：前面这些页服务端已经收下了
  let sid = imp.stageId || '';
  let id = imp.resumeId || '';   // 普通书上传中断时接着往这本书里补
  let added = 0;
  let skipped = 0;
  let sent = base;
  let phase = 'upload';

  try {
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const fd = new FormData();
      chunk.forEach(f => fd.append('files', f, f.name));
      fd.append('batch', `${runId}-${i}`);   // 幂等：同一批重试不会写两遍

      if (sid) {
        fd.append('append', sid);
      } else if (id) {
        fd.append('append', id);
      } else if (cover) {
        fd.append('stage', '1');
        fd.append('target', cover);
        fd.append('expect', String(total));
        fd.append('title', title);
        fd.append('author', $('#impAuthor').value.trim());
        // 分类与可见性不传：更新图片不该顺手改这两项，服务端沿用旧书的值
      } else {
        fd.append('title', title);
        fd.append('author', $('#impAuthor').value.trim());
        fd.append('cat', $('#impCat').value);
        if ($('#impHidden').checked) fd.append('hidden', '1');
        if (opts.duplicate) fd.append('allow_duplicate', '1');
      }

      const a = base + i + 1, b = base + i + chunk.length;
      const range = `${a}–${b}`;
      const head = cover ? '正在上传新图' : '正在处理';
      impMsg(`${head} 第 ${range} 页 / 共 ${total} 页…`);
      const j = await uploadRetry('/api/import/images', fd, pct => {
        impMsg(`${head} 第 ${range} 页 / 共 ${total} 页 · ${pct}%`);
      }, 3);

      if (j.staging) {
        sid = j.staging;
        imp.stageId = sid;
        imp.stageTarget = j.target || cover;
      } else if (j.id) {
        id = j.id;
      }
      added += j.added || 0;
      skipped += j.skipped || 0;
      sent = b;
      imp.sent = sent;          // 实时记进度，中断后从这里续
    }

    let finalId = id;
    if (sid) {
      // 覆盖更新：所有页都收齐了，才让服务端校验并原子替换
      phase = 'commit';
      impMsg(`已收到 ${added} 页，正在校验页数并替换…`);
      const cfd = new FormData();
      cfd.append('stage', sid);
      cfd.append('target', imp.stageTarget || cover);
      const c = await uploadRetry('/api/import/images/commit', cfd, null, 3);
      finalId = c.id || imp.stageTarget;
      const back = await fetch('/api/book/' + encodeURIComponent(finalId)).then(r => r.json());
      const got = (back.toc || []).length;
      if (back.type !== 'image') throw new Error('替换后不是图片书，已中止');
      if (total && got !== total) throw new Error(`替换后只有 ${got} 页，应为 ${total} 页`);
    }

    return await imageDone(finalId);
  } catch (e) {
    imp.busy = false;
    $('#impGo').disabled = false;
    imp.chain = 0;
    const extra = skipped ? `（${skipped} 页被跳过）` : '';
    const detail = (e.body && e.body.detail) || {};

    // 同名冲突：问要不要覆盖
    if (e.status === 409 && detail.conflict && !cover && !opts.duplicate) {
      const d = detail.conflict;
      const multi = (d.count || 1) > 1
        ? `\n（书库里有 ${d.count} 本同名书，将更新其中最近导入的一本）` : '';
      const yes = confirm(
        `已存在同名书籍《${d.title || title}》${d.n ? '（' + d.n + ' 页/节）' : ''}。${multi}\n\n` +
        '确定：用这批图片替换它（新图全部收齐并校验通过后才替换，失败则旧内容不变；替换后不可回退）；\n' +
        '取消：另存为一本新书。'
      );
      if (yes) await doImportImages({ replace: d.id || '' });
      else await doImportImages({ duplicate: true });
      return;
    }

    // 提交阶段出错：先探明服务端到底提交成功没有，别把成功报成失败
    if (phase === 'commit' && sid) {
      const v = await stageVerdict(sid, imp.stageTarget || cover, total);
      if (v === 'committed') {
        impMsg('更新已完成（提交回执丢失，但已核实页数一致）', 'ok');
        return await imageDone(imp.stageTarget || cover);
      }
      if (v === 'pending') {
        $('#impGo').textContent = '再次提交';
        impMsg(`旧书未做任何改动。新图已在服务端就绪（${total} 页），但替换这一步没走完：` +
               `${e.message || e}。点「再次提交」重试，不需要重新上传。`, 'err');
        return;
      }
      dropStage();
      impMsg(`旧书未做任何改动，但无法确认替换结果：${e.message || e}。请打开这本书核对，必要时重新导入。`, 'err');
      return;
    }

    // 上传中途失败：旧书没动，已收的页留在服务端，接着传就行
    if (sid && sent < total) {
      $('#impGo').textContent = '继续上传';
      impMsg(`旧书未做任何改动。已暂存 ${sent} / ${total} 页，传输中断：${e.message || e}${extra}。` +
             `点「继续上传」只补剩下的 ${total - sent} 页。`, 'err');
      return;
    }

    if (sid) {
      dropStage();
      $('#impGo').textContent = '重新导入';
      impMsg(`旧书未做任何改动。${e.message || e}${extra}。请检查这批图片后重新导入。`, 'err');
      return;
    }

    // 普通新建/追加：已经建好书、只是后面几批失败，记住断点只补剩余页
    if (id && sent < total) {
      imp.resumeId = id;
      $('#impGo').textContent = '继续上传';
      impMsg(`已传 ${sent} / ${total} 页，后面失败了：${e.message || e}${extra}。` +
             `点「继续上传」只补剩下的 ${total - sent} 页。`, 'err');
      return;
    }
    impMsg(String(e.message || e) + extra, 'err');
  }
}

/* ---------- 导入面板：统一拖放区 ---------- */
$('#impDrop').addEventListener('click', () => $('#impFile').click());
$('#impDrop').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#impFile').click(); }
});
const pdEl = $('#impPickDir');
if (pdEl) {
  pdEl.addEventListener('click', e => {
    e.stopPropagation();          // 别同时弹出「选文件」
    $('#impDir').click();
  });
}
$('#impPickZip').addEventListener('click', e => {
  e.stopPropagation();
  $('#impFile').click();
});

$('#impFile').addEventListener('change', e => {
  takeFiles(e.target.files);
  e.target.value = '';            // 允许重复选同一批文件
});
$('#impDir').addEventListener('change', e => {
  takeFiles(e.target.files);
  e.target.value = '';
});

['dragenter', 'dragover'].forEach(t => $('#impDrop').addEventListener(t, e => {
  e.preventDefault(); $('#impDrop').classList.add('over');
}));
['dragleave', 'drop'].forEach(t => $('#impDrop').addEventListener(t, e => {
  e.preventDefault(); $('#impDrop').classList.remove('over');
}));
$('#impDrop').addEventListener('drop', async e => {
  if (imp.dragFrom >= 0) return;  // 内部缩略图在拖动，不是外部文件
  const files = await filesFromDrop(e.dataTransfer);
  if (files.length) takeFiles(files);
});

/* 排序下拉：名称 / 时间 / 手动 */
$('#impSort').addEventListener('change', e => {
  imp.sort = e.target.value;
  applySort();
  renderImages();
  impMsg(stageHint(), 'ok');
});

/* 缩略图拖动排序：松手即生效，并把排序切到「手动」 */
const pv = $('#imgPrev');
pv.addEventListener('dragstart', e => {
  const it = e.target.closest('.pgitem');
  if (!it) return;
  imp.dragFrom = +it.dataset.i;
  it.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  try { e.dataTransfer.setData('text/plain', String(imp.dragFrom)); } catch (err) { }
});
pv.addEventListener('dragend', () => {
  imp.dragFrom = -1;
  [...pv.children].forEach(x => x.classList.remove('dragging', 'over'));
});
pv.addEventListener('dragover', e => {
  if (imp.dragFrom < 0) return;
  e.preventDefault();
  e.stopPropagation();            // 别让外层拖放区跟着高亮
  const it = e.target.closest('.pgitem');
  [...pv.children].forEach(x => x.classList.toggle('over', x === it && +x.dataset.i !== imp.dragFrom));
});
pv.addEventListener('dragleave', e => {
  const it = e.target.closest('.pgitem');
  if (it) it.classList.remove('over');
});
pv.addEventListener('drop', e => {
  if (imp.dragFrom < 0) return;
  e.preventDefault();
  e.stopPropagation();
  const it = e.target.closest('.pgitem');
  if (it) moveImage(imp.dragFrom, +it.dataset.i);
  imp.dragFrom = -1;
});

/* 触屏没有 hover、也没有 HTML5 拖放：去掉「手动拖动」，改用 ✕ 删页 */
if (window.matchMedia('(hover:none)').matches) {
  const opt = $('#impSort').querySelector('option[value="manual"]');
  if (opt) opt.remove();
  $('#imgHint').textContent = '点缩略图右上角 ✕ 可移除某一页';
}

async function delBook() {
  const b = state.book;
  if (!b) return;
  const ok = confirm('把《' + b.title + '》彻底删除？\n\n' +
    '正文、图片页、译文缓存和目录译名都会立即清除，无法恢复。');
  if (!ok) return;
  const token = prompt('删除《' + b.title + '》需要管理口令（服务端 ADMIN_TOKEN）：');
  if (token == null) return;
  const r = await fetch('/api/book/' + b.id, {
    method: 'DELETE',
    headers: { 'X-Admin-Token': token },
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = j.detail;
    alert(typeof d === 'string' ? d : ('删除失败 ' + r.status));
    return;
  }
  closeReader();
  await loadShelf(state.hidden);
}

$('#impBtn').addEventListener('click', openImp);
$('#impModal').addEventListener('click', e => {
  if (e.target.closest('[data-close]')) closeImp();
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
  if (imp.images.length) return;              // 暂存区已有图片，正文框是收起的
  e.preventDefault();
  if (imp.mode === 'file') { impMsg('已选文件，先点「清除」再粘贴正文', 'err'); return; }
  const ta = $('#impText');
  const cur = ta.value.replace(/\s*$/, '');
  const total = (cur ? cur.length + 2 : 0) + t.length;
  if (total > 6000000) { impMsg('粘贴内容超过 600 万字，请存成文件后拖入', 'err'); return; }
  ta.value = (cur ? cur + '\n\n' : '') + t;
  impMsg(`已粘贴 ${t.length.toLocaleString()} 字，可继续粘贴，或点「导入并阅读」`, 'ok');
});
/* 提交：按暂存内容决定建几本。文本先入库（快），图片走后台上传。 */
async function submit() {
  if (imp.busy) return;
  const typed = ($('#impText').value || '').trim();
  const text = (imp.mode === 'file' && imp.text) ? imp.text : typed;
  const n = imp.images.length;

  if (!text && !n) return impMsg('请先选择文件、图片，或粘贴正文', 'err');
  if (text && text.length < 200) return impMsg('正文太短，至少 200 字', 'err');
  if (text.length > 6000000) return impMsg('正文超过 600 万字，请先拆分', 'err');

  const hasT = !!text;
  imp.chain = (hasT ? 1 : 0) + (n ? 1 : 0);
  imp.lastId = '';

  if (hasT) await doImport();
  if (n && imp.chain > 0) await doImportImages({ titleOverride: hasT ? '' : undefined });
}

$('#impGo').addEventListener('click', submit);
$('#delBtn').addEventListener('click', delBook);
$('#impText').addEventListener('input', () => { if ($('#impText').value.trim()) impMsg(''); });
