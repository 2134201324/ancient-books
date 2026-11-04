#!/usr/bin/env python3
"""英文公版书解析：去 Gutenberg 头尾 -> 分章 -> 段落还原"""
import re

START = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\*\*\*", re.I)
END = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\*\*\*", re.I)

ROMAN = r"[IVXLCDM]+"
HEAD_PATTERNS = [
    ("章", re.compile(rf"^(?:CHAPTER|Chapter|CHAP\.?)\s+({ROMAN}|\d{{1,3}})\b[.:]?\s*(.{{0,200}})$")),
    ("卷", re.compile(rf"^(?:BOOK|Book|PART|Part|VOLUME|Volume)\s+({ROMAN}|\d{{1,3}})\b[.:]?\s*(.{{0,200}})$")),
    ("篇", re.compile(rf"^(?:CANTO|Canto|LETTER|Letter|SECTION|Section|LECTURE|Lecture|SCENE|Scene|QUESTION|Question|PSALM|Psalm)\s+({ROMAN}|\d{{1,3}})\b[.:]?\s*(.{{0,200}})$")),
    ("章", re.compile(rf"^({ROMAN})\.\s*$")),
    ("篇", re.compile(r"^(LIFE|Life) OF [A-Z][A-Z' \-]{2,60}\.?$")),
    ("章", re.compile(rf"^(?:ADVENTURE|Adventure)\s+({ROMAN}|\d{{1,2}})\.?\s*(.{{0,200}})$")),
    ("篇", re.compile(r"^(THE|The) (STORY|Story|TALE|Tale) OF [A-Z][A-Za-z' \-]{2,60}$")),
]

NOISE = [
    re.compile(r"^\s*\[(Illustration|Ill\.|Plate|Figure|Diagram|Map)[^\]]*\]\s*$", re.I),
    re.compile(r"^\s*\[[A-Z][^\]]{0,80}\]\s*$"),
    re.compile(r"^\s*(Produced by|Transcriber|E-text prepared|HTML version|Updated editions)", re.I),
]


def strip_pg(t):
    m = START.search(t)
    if m:
        t = t[m.end():]
    m = END.search(t)
    if m:
        t = t[:m.start()]
    return t.strip()


def clean(t):
    out = []
    for ln in t.split("\n"):
        s = ln.rstrip()
        if any(r.match(s) for r in NOISE):
            continue
        out.append(s)
    return out


def restore_paras(lines):
    """英文段落：空行分隔，行内用空格连接"""
    paras, buf = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf))
    # 清理标记：下划线斜体、多余空格
    out = []
    for p in paras:
        p = re.sub(r"[_*]{1,2}([^_*]{1,120})[_*]{1,2}", r"\1", p)
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) >= 2:
            out.append(p)
    return out


def head_of(s):
    s = s.strip()
    if len(s) > 210:
        return None
    for kind, rx in HEAD_PATTERNS:
        m = rx.match(s)
        if not m:
            continue
        g = m.groups()
        if len(g) == 1:
            return kind, s.strip(" .")
        num = g[0]
        rest = (g[1] or "").strip(" .:—-")
        rest = re.sub(r"\[\d{1,3}\]", "", rest).strip(" .:—-")
        # 标题行后紧跟正文句子时（如 "BOOK I. The Republic opens with..."），不并入标题
        if rest and not rest.isupper() and len(rest) > 45:
            rest = ""
        head = s.split()[0].title()
        title = f"{head} {num}" if not rest else f"{head} {num} · {rest[:190]}"
        return kind, title
    return None


def head_key(s):
    """取标题行的 (章节词, 编号)，用于目录/正文标题对齐。"""
    m = re.match(r"^\s*([A-Za-z]+)\s+(\d{1,3}|[IVXLCDM]+)\b", s or "")
    return (m.group(1).title(), m.group(2)) if m else None


def parse(text, fallback=True):
    lines = clean(strip_pg(text))
    heads = []
    for i, raw in enumerate(lines):
        h = head_of(raw)
        if h:
            heads.append((i, h[1], h[0]))
    if len(heads) < 4:
        paras = restore_paras(lines)
        if fallback and sum(len(p) for p in paras) > 40000:
            return chunk(paras, 24000), "节", sum(len(p.split()) for p in paras)
        return [{"title": "Full text", "paras": paras}], "单", sum(len(p.split()) for p in paras)

    # 合并紧跟标题行的副标题（可为多行全大写折行，如 CHAPTER IV. + 两行说明）
    fixed = []
    for i, title, k in heads:
        j = i + 1
        extra = []
        while len(extra) < 3:
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                break
            nxt = lines[j].strip()
            if not nxt or len(nxt) > 130 or head_of(nxt):
                break
            if nxt.isupper():
                extra.append(nxt.rstrip("."))
                j += 1
                continue
            break
        if extra:
            sub = " ".join(x.rstrip(" ,;:—-") for x in extra)
            title = (title + " " + sub) if "·" in title else f"{title} · {sub}"
            fixed.append((i, title, k, j))
        else:
            fixed.append((i, title, k, i + 1))
    heads = fixed

    chapters = []
    pre = restore_paras(lines[:heads[0][0]])
    if sum(len(p) for p in pre) > 1200:
        chapters.append({"title": "序言 · Front Matter", "paras": pre})
    for k, (i, title, _k, start) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = restore_paras(lines[start:end])
        if sum(len(p) for p in body) < 400:
            continue
        chapters.append({"title": title, "paras": body})
    sizes = [sum(len(p) for p in c["paras"]) for c in chapters]
    if fallback and sizes and (max(sizes) > 350000 or (len(chapters) <= 5 and sum(sizes) > 120000)):
        paras = restore_paras(lines)
        return chunk(paras, 30000), "节", sum(len(p.split()) for p in paras)

    return chapters, "章", sum(len(p.split()) for c in chapters for p in c["paras"])


def chunk(paras, size):
    out, buf, n = [], [], 0
    for p in paras:
        buf.append(p)
        n += len(p)
        if n >= size:
            out.append({"title": f"第 {len(out)+1} 节", "paras": buf})
            buf, n = [], 0
    if buf:
        out.append({"title": f"第 {len(out)+1} 节", "paras": buf})
    return out
