"""用户导入：把纯文本切成章节，写进书库数据。

设计要点
- 不依赖第三方解析库，只认「第X章 / Chapter N / 卷一 / 序」这类行首标题；
  识别不到就按长度切片，保证任何纯文本都能读。
- 目录页（只有标题、没有正文的行）会被自动丢弃，避免出现一堆空章节。
- 导入的书和内置书同构：同一个 gz 结构、同一套接口、同样可翻译。
- 写入用 tmp + os.replace，导入失败不会留下半个文件。
"""
from __future__ import annotations

import gzip
import json
import os
import random
import re
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BOOKS = os.path.join(DATA, "books")
LIB_PATH = os.path.join(DATA, "library.json")

CATS = ["小说", "历史", "哲学", "诗文", "社科", "科学", "戏曲", "蒙学", "文学", "其他"]

# 行首标题：第X章/回/节/卷/篇/部/集、序类、Chapter/Book/Part N
HEAD = re.compile(
    r"^\s*(?:"
    r"第[零〇一二三四五六七八九十百千两0-9]{1,9}[章回节卷篇部集](?:[\s:：、.．·-].*)?"
    r"|(?:序章|序言|自序|原序|楔子|引子|前言|后记|尾声|结语|附录|凡例|跋)(?:[\s:：、.．].*)?"
    r"|(?:Chapter|CHAPTER|Book|BOOK|Part|PART)\s+[IVXLCDMivxlcdm0-9]+(?:[\s:：、.．-].*)?"
    r")\s*$"
)

CJK = re.compile(r"[\u4e00-\u9fa5]")
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
WEN = re.compile(r"[之乎者也矣焉哉曰其而乃遂亦皆莫非未]")
BAI = re.compile(r"(?:的|了|着|们|这|那|是|他|你|我|就|都|很|把|被|给|没|个)")


def norm_text(text: str) -> str:
    text = (text or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    # 去掉连续空行，保留段落分隔
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_lang(text: str) -> str:
    cjk = len(CJK.findall(text))
    latin = len(WORD.findall(text))
    return "zh" if cjk >= max(80, latin) else "en"


def wen_ratio(text: str) -> float:
    """文言系数：虚词密度 / 白话虚词密度，越大越文言。"""
    n = max(1, len(text))
    a = len(WEN.findall(text)) * 1000 / n
    b = len(BAI.findall(text)) * 1000 / n
    return round(a / (b + 1.0), 2)


def _split_by_head(text: str) -> list[tuple[str, str]]:
    lines = text.split("\n")
    marks: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or len(s) > 60:
            continue
        if HEAD.match(s):
            # 标题行通常前后有空行；紧跟长句的「第一章……」更可能是正文引用
            before = lines[i - 1].strip() if i > 0 else ""
            after = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if (not before or not after) or (len(before) < 80 and len(after) < 200):
                marks.append((i, s))
    if len(marks) < 2:
        return []

    out: list[tuple[str, str]] = []
    head = "\n".join(lines[: marks[0][0]]).strip()
    if len(head) > 200:
        out.append(("卷首", head))
    for j, (i, title) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i + 1 : end]).strip()
        out.append((title, body))
    return out


def _hard_split(p: str, size: int) -> list[str]:
    """超长段落按句读硬切，尽量不切断句子。"""
    out = []
    while len(p) > size:
        cut = max(p.rfind(x, 0, size) for x in "。！？；!?;\n")
        cut = cut + 1 if cut >= size * 0.4 else size
        out.append(p[:cut])
        p = p[cut:]
    if p:
        out.append(p)
    return out


def _split_by_size(text: str, size: int = 6000) -> list[tuple[str, str]]:
    units = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(units) <= 1:
        units = [p.strip() for p in text.split("\n") if p.strip()]
    out: list[tuple[str, str]] = []
    buf: list[str] = []
    n = 0

    def flush() -> None:
        nonlocal buf, n
        if buf:
            out.append((f"第 {len(out) + 1} 节", "\n".join(buf)))
            buf, n = [], 0

    for p in units:
        if len(p) > size:
            flush()
            for piece in _hard_split(p, size):
                out.append((f"第 {len(out) + 1} 节", piece))
            continue
        if n + len(p) > size:
            flush()
        buf.append(p)
        n += len(p)
    flush()
    return out


def split_chapters(text: str) -> tuple[list[dict], str]:
    """返回 (章节列表, 单位)。空章节（目录页残留）会被丢弃。"""
    segs = _split_by_head(text)
    kind = "节"
    if segs:
        for t, _ in segs:
            m = re.search(r"第[零〇一二三四五六七八九十百千两0-9]{1,9}([章回节卷篇部集])", t)
            if m:
                kind = m.group(1)
                break
            if re.match(r"(?i)(chapter|book|part)", t):
                kind = "章"
                break

    chs = [{"title": t, "text": b} for t, b in segs if b.strip()]
    # 全是空标题（整本是目录）时退回按长度切
    if len(chs) < 2:
        chs, kind = [{"title": t, "text": b} for t, b in _split_by_size(text)], "节"

    # 超长单章再切一刀，避免一次返回几兆正文
    fine: list[dict] = []
    for c in chs:
        if len(c["text"]) <= 20000:
            fine.append(c)
            continue
        for i, (_t, b) in enumerate(_split_by_size(c["text"], 8000)):
            fine.append({"title": f"{c['title']}（{i + 1}）", "text": b})
    return fine, kind


def new_id() -> str:
    ts = ""
    n = int(time.time() * 1000)
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    while n:
        n, r = divmod(n, 36)
        ts = alphabet[r] + ts
    return "u" + ts + "".join(random.choice(alphabet) for _ in range(4))


def build(title: str, author: str, text: str, cat: str = "其他") -> dict:
    text = norm_text(text)
    chapters, kind = split_chapters(text)
    lang = detect_lang(text)
    chars = len(re.findall(r"[^\s]", text))
    words = len(WORD.findall(text))
    cat = cat if cat in CATS else "其他"
    return {
        "id": new_id(),
        "title": (title or "未命名").strip()[:120],
        "author": (author or "佚名").strip()[:120],
        "lang": lang,
        "cat": cat,
        "kind": kind,
        "chars": chars,
        "words": words,
        "n": len(chapters),
        "ok": True,
        "has_cn": False,
        "wen": wen_ratio(text) if lang == "zh" else 0,
        "source": "user",
        "added": int(time.time()),
        "chapters": chapters,
    }


_lock = threading.Lock()


def save(book: dict) -> None:
    """写书 + 追加书库索引，两步都原子替换。"""
    with _lock:
        os.makedirs(BOOKS, exist_ok=True)
        path = os.path.join(BOOKS, book["id"] + ".json.gz")
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(book, f, ensure_ascii=False)
        os.replace(tmp, path)

        lib = []
        if os.path.exists(LIB_PATH):
            with open(LIB_PATH, encoding="utf-8") as f:
                lib = json.load(f) or []
        lib = [b for b in lib if b.get("id") != book["id"]]
        lib.append({k: v for k, v in book.items() if k != "chapters"})
        tmp = LIB_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False)
        os.replace(tmp, LIB_PATH)


def delete(bid: str) -> bool:
    with _lock:
        path = os.path.join(BOOKS, bid + ".json.gz")
        if not os.path.exists(path):
            return False
        os.remove(path)
        if os.path.exists(LIB_PATH):
            with open(LIB_PATH, encoding="utf-8") as f:
                lib = json.load(f) or []
            lib = [b for b in lib if b.get("id") != bid]
            tmp = LIB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(lib, f, ensure_ascii=False)
            os.replace(tmp, LIB_PATH)
        return True
