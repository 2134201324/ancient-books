"""墨读 · 公版书库（中文古籍 + 西方典籍）"""
import gzip
import json
import os
import re
import threading
import time
from functools import lru_cache

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import trans
from trans import translate_chapter

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BOOKS = os.path.join(DATA, "books")
STATIC = os.path.join(BASE, "static")

app = FastAPI(title="墨读 · 公版书库")

CATS = ["小说", "历史", "哲学", "诗文", "社科", "科学", "戏曲", "蒙学", "文学", "其他"]


def _lib():
    with open(os.path.join(DATA, "library.json"), encoding="utf-8") as f:
        return json.load(f)


LIB = _lib()
INDEX = [
    {
        "id": b["id"],
        "title": b["title"],
        "author": b["author"],
        "chars": b["chars"],
        "words": b.get("words", 0),
        "n": b["n"],
        "ok": b["ok"],
        "kind": b["kind"],
        "cat": b.get("cat", "其他"),
        "lang": b.get("lang", "zh"),
        "subject": b.get("subject", []),
        "w": b["chars"] if b.get("lang", "zh") == "zh" else int(b.get("words", 0) * 1.55),
        "has_cn": bool(b.get("has_cn", False)),
        "wen": b.get("wen", 0),
    }
    for b in LIB
]
META = {b["id"]: b for b in LIB}


def _can_modern(b: dict) -> bool:
    """是否提供文言今译。小说类门槛更高，避免把白话公案/世情小说当成文言改写。"""
    if b.get("lang", "zh") != "zh":
        return False
    cat = b.get("cat") or META.get(b["id"], {}).get("cat", "")
    wen = float(META.get(b["id"], {}).get("wen") or 0)
    return wen >= (3.0 if cat == "小说" else 2.0)


@lru_cache(maxsize=8)
def _load_book(bid: str) -> dict:
    path = os.path.join(BOOKS, f"{bid}.json.gz")
    if not os.path.exists(path):
        raise HTTPException(404, "书不存在")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _has_cn(b: dict) -> bool:
    if b.get("has_cn") or any(c.get("cn") for c in b["chapters"]):
        return True
    return trans.book_has_cn(b["id"])


def _with_cache(b: dict, idx: int) -> dict:
    """把磁盘上的实时译文补进章节（不改动原始书籍文件）。"""
    c = b["chapters"][idx]
    if not c.get("cn"):
        hit = trans.load_cache(b["id"], idx)
        if hit and hit.get("cn"):
            c["cn"] = hit["cn"]
            if hit.get("cn_title"):
                c["cn_title"] = hit["cn_title"]
    return c


_persist_lock = threading.Lock()


def _persist_book(bid: str) -> None:
    """把缓存里已完成的译文合并进书籍文件。

    这样译文不再只是「某台机器的临时缓存」，而是书籍数据的一部分：
    服务重启、换实例、重新发布都不会丢，其他用户打开直接读中文。
    只合并 done=True 且段落数与原文严格一致的章节，避免半成品。
    """
    path = os.path.join(BOOKS, f"{bid}.json.gz")
    if not os.path.exists(path):
        return
    with _persist_lock:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                book = json.load(f)
            chs = book.get("chapters") or []
            changed = 0
            for i, ch in enumerate(chs):
                if ch.get("cn"):
                    continue
                hit = trans.load_cache(bid, i)
                if not hit or not hit.get("done"):
                    continue
                cn = hit.get("cn") or []
                if len(cn) != len(ch["text"].split("\n")) or not any(x.strip() for x in cn):
                    continue
                ch["cn"] = cn
                if hit.get("cn_title"):
                    ch["cn_title"] = hit["cn_title"]
                changed += 1
            if not changed:
                return
            book["has_cn"] = True
            tmp = path + ".tmp"
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(book, f, ensure_ascii=False)
            os.replace(tmp, path)
            _load_book.cache_clear()
            print(f"[persist] {bid}: {changed} 章译文已并入书籍数据", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[persist] {bid} 合并失败: {type(e).__name__}: {e}", flush=True)


CJK = re.compile(r"[\u4e00-\u9fa5]")
TITLES_PATH = os.path.join(DATA, "cn_titles.json")
_titles_state = {"mtime": -1.0, "data": {}}


def cn_titles(bid: str) -> list:
    """目录中文标题表（离线批量生成），文件变更时自动重载。"""
    m = os.path.getmtime(TITLES_PATH) if os.path.exists(TITLES_PATH) else 0
    if m != _titles_state["mtime"]:
        try:
            with open(TITLES_PATH, encoding="utf-8") as f:
                _titles_state["data"] = json.load(f) or {}
        except Exception:
            _titles_state["data"] = {}
        _titles_state["mtime"] = m
    rec = _titles_state["data"].get(bid) or {}
    return rec.get("t") or []


_mf_state = {"at": 0.0, "data": {}}


def _manifest(ttl: float = 3.0) -> dict:
    """译文清单短缓存：书架是高频接口，避免每次都扫目录。"""
    now = time.time()
    if now - _mf_state["at"] > ttl:
        _mf_state["data"] = trans.manifest()
        _mf_state["at"] = now
    return _mf_state["data"]


@app.get("/api/library")
def library(q: str = "", sort: str = "chars", cat: str = ""):
    # 实时译文按磁盘清单覆盖，避免实时翻译过的书在书架上没有「译」角标
    mf = _manifest()
    items = [dict(x, has_cn=bool(x["has_cn"] or (m := mf.get(x["id"])) and m["n"])) for x in INDEX]
    if cat:
        items = [x for x in items if x["cat"] == cat]
    if q:
        ql = q.strip().lower()
        items = [x for x in items if ql in x["title"].lower() or ql in x["author"].lower()]
    if sort == "title":
        items = sorted(items, key=lambda x: x["title"])
    elif sort == "author":
        items = sorted(items, key=lambda x: x["author"])
    else:
        items = sorted(items, key=lambda x: -x["w"])
    return {"total": len(items), "items": items}


@app.get("/api/book/{bid}")
def book_meta(bid: str):
    b = _load_book(bid)
    chs = b["chapters"]
    has_cn = _has_cn(b)
    lang = b.get("lang", "zh")
    can_modern = _can_modern(b)
    cts = trans.titles(b["id"])
    static = cn_titles(b["id"])
    toc = []
    for i, c in enumerate(chs):
        ct = c.get("cn_title") or ""
        if not ct and i < len(static) and CJK.search(static[i] or ""):
            ct = static[i]
        if not ct:
            ct = cts.get(i, "")
        toc.append({"i": i, "t": c["title"], "ct": ct})
    return {
        "id": b["id"],
        "title": b["title"],
        "author": b["author"],
        "chars": b["chars"],
        "words": b.get("words", 0),
        "kind": b["kind"],
        "cat": b.get("cat", "其他"),
        "lang": lang,
        "ok": b["ok"],
        "has_cn": has_cn,
        # mode: en2zh = 英译中；zh2modern = 文言今译；空 = 无可切换译文
        "mode": "en2zh" if lang == "en" else ("zh2modern" if can_modern else ""),
        "can_modern": can_modern,
        "translate": bool(trans.enabled() and (lang == "en" or can_modern)),
        "toc": toc,
    }


@app.get("/api/book/{bid}/ch/{idx}")
def chapter(bid: str, idx: int):
    b = _load_book(bid)
    chs = b["chapters"]
    if idx < 0 or idx >= len(chs):
        raise HTTPException(404, "章节不存在")
    c = _with_cache(b, idx)
    nxt = chs[idx + 1]["title"] if idx + 1 < len(chs) else None
    prev = chs[idx - 1]["title"] if idx > 0 else None
    return {
        "i": idx,
        "title": c["title"],
        "paras": c["text"].split("\n"),
        "cn": c.get("cn") or [],
        "cnTitle": c.get("cn_title") or "",
        "next": nxt,
        "prev": prev,
    }


@app.get("/api/translate/status")
def translate_status():
    return trans.status()


@app.get("/api/cn/manifest")
def cn_manifest():
    """已落盘译文的清单：{书号: {n, done}}。用于书架角标与外部同步。"""
    return {"books": trans.manifest()}


@app.get("/api/cn/export")
def cn_export(book: str = ""):
    """导出已翻译内容（全部或用 ?book= 指定一本），供备份/迁移进发布包。"""
    if book:
        rec = trans.export_book(book)
        if not rec:
            raise HTTPException(404, "没有该书译文")
        return rec
    return trans.export_all()


@app.post("/api/book/{bid}/ch/{idx}/translate")
def translate(bid: str, idx: int):
    """流式返回翻译过程：meta / part / prog / done / err。"""
    b = _load_book(bid)
    if idx < 0 or idx >= len(b["chapters"]):
        raise HTTPException(404, "章节不存在")
    if b.get("lang", "zh") != "en" and not _can_modern(b):
        raise HTTPException(400, "该书为白话文本，无需今译")
    if not trans.enabled():
        raise HTTPException(503, "翻译服务未配置")

    def sse():
        try:
            for ev in translate_chapter(b, idx):
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
                # 新译完整章时并入书籍数据；缓存命中说明此前已落盘，无需重复写整本
                if ev.get("t") == "done" and not ev.get("cached"):
                    threading.Thread(target=_persist_book, args=(bid,), daemon=True).start()
        except Exception as e:  # noqa: BLE001
            payload = {"t": "err", "msg": str(e)[:300]}
            yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------- 阅读状态（服务端）
# 书正文、译文、目录译名全部在服务端；这里再把「读到第几章 / 最近在读」也存到服务端，
# 浏览器只保留一个随机设备号。换设备、清缓存都不会丢进度。
USERS = os.path.join(DATA, "users")
CID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
_state_lock = threading.Lock()


def _state_path(cid: str) -> str:
    return os.path.join(USERS, cid + ".json")


def _read_state(cid: str) -> dict:
    p = _state_path(cid)
    if not os.path.exists(p):
        return {"recent": [], "pos": {}, "prefs": {}}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f) or {}
    except Exception:
        return {"recent": [], "pos": {}, "prefs": {}}
    return {
        "recent": d.get("recent") or [],
        "pos": d.get("pos") or {},
        "prefs": d.get("prefs") or {},
    }


def _merge_state(old: dict, new: dict) -> dict:
    """按时间戳取新：最近在读按书去重，进度按书写入，偏好浅合并。"""
    recent = {}
    for x in list(old.get("recent") or []) + list(new.get("recent") or []):
        if not isinstance(x, dict):
            continue
        bid = str(x.get("id") or "")[:64]
        if not bid:
            continue
        t = int(x.get("t") or 0)
        cur = recent.get(bid)
        if cur is None or t >= cur["t"]:
            recent[bid] = {"id": bid, "ci": max(0, int(x.get("ci") or 0)), "t": t}

    pos = {}
    for src in (old.get("pos") or {}, new.get("pos") or {}):
        if not isinstance(src, dict):
            continue
        for bid, v in src.items():
            bid = str(bid)[:64]
            if isinstance(v, dict):
                i, t = int(v.get("i") or 0), int(v.get("t") or 0)
            else:
                i, t = int(v or 0), 0
            cur = pos.get(bid)
            if cur is None or t >= cur["t"]:
                pos[bid] = {"i": max(0, i), "t": t}

    prefs = dict(old.get("prefs") or {})
    if isinstance(new.get("prefs"), dict):
        prefs.update(new["prefs"])
    return {
        "recent": sorted(recent.values(), key=lambda x: -x["t"])[:24],
        "pos": dict(sorted(pos.items(), key=lambda kv: -kv[1]["t"])[:500]),
        "prefs": prefs,
    }


@app.get("/api/state/{cid}")
def get_state(cid: str):
    if not CID_RE.match(cid):
        raise HTTPException(400, "设备号不合法")
    return _read_state(cid)


@app.put("/api/state/{cid}")
def put_state(cid: str, payload: dict = Body(...)):
    if not CID_RE.match(cid):
        raise HTTPException(400, "设备号不合法")
    if len(json.dumps(payload, ensure_ascii=False)) > 262144:
        raise HTTPException(413, "状态过大")
    with _state_lock:
        merged = _merge_state(_read_state(cid), payload)
        os.makedirs(USERS, exist_ok=True)
        p = _state_path(cid)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False)
        os.replace(tmp, p)
    return {"ok": True, "recent": len(merged["recent"]), "pos": len(merged["pos"])}


@app.get("/api/stats")
def stats():
    cats = {}
    for x in INDEX:
        cats[x["cat"]] = cats.get(x["cat"], 0) + 1
    return {
        "books": len(INDEX),
        "complete": sum(1 for x in INDEX if x["ok"]),
        "chars": sum(x["chars"] for x in INDEX if x["lang"] == "zh"),
        "words": sum(x["words"] for x in INDEX if x["lang"] == "en"),
        "chinese": sum(1 for x in INDEX if x["lang"] == "zh"),
        "western": sum(1 for x in INDEX if x["lang"] == "en"),
        "cats": [{"name": c, "n": cats[c]} for c in CATS if cats.get(c)],
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
