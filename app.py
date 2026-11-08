"""墨读 · 公版书库（中文古籍 + 西方典籍）"""
import gzip
import hmac
import json
import os
import re
import shutil
import threading
import time
from functools import lru_cache

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import comic
import importer
import trans
from trans import translate_chapter

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BOOKS = os.path.join(DATA, "books")
MEDIA = os.path.join(DATA, "media")
STATIC = os.path.join(BASE, "static")

app = FastAPI(title="墨读 · 公版书库")

CATS = ["小说", "历史", "哲学", "诗文", "社科", "科学", "戏曲", "蒙学", "文学", "其他"]


def _lib():
    with open(os.path.join(DATA, "library.json"), encoding="utf-8") as f:
        return json.load(f)


def _index(lib: list) -> list:
    return [
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
            "has_cn": bool(b.get("has_cn", False)),
            "wen": b.get("wen", 0),
            "source": b.get("source", ""),
            "hidden": bool(b.get("hidden")),
            "type": b.get("type", "text"),
            "w": (b["n"] * 2500) if b.get("type") == "image" else
                 (b["chars"] if b.get("lang", "zh") == "zh" else int(b.get("words", 0) * 1.55)),
        }
        for b in lib
    ]


LIB = _lib()
INDEX = _index(LIB)
META = {b["id"]: b for b in LIB}


def reload_library() -> None:
    """导入/删除后重建内存索引，让书架立刻看到变化。"""
    global LIB, INDEX, META
    LIB = _lib()
    INDEX = _index(LIB)
    META = {b["id"]: b for b in LIB}
    _load_book.cache_clear()


def _can_modern(b: dict) -> bool:
    """是否提供文言今译。小说类门槛更高，避免把白话公案/世情小说当成文言改写。"""
    if b.get("lang", "zh") != "zh":
        return False
    cat = b.get("cat") or META.get(b["id"], {}).get("cat", "")
    wen = float(META.get(b["id"], {}).get("wen") or 0)
    return wen >= (3.0 if cat == "小说" else 2.0)


@lru_cache(maxsize=3)   # 个人阅读同时只翻一两本，留 3 本足够，省下几百兆常驻内存
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
            merged: list[int] = []
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
                merged.append(i)
            if not changed:
                return
            book["has_cn"] = True
            tmp = path + ".tmp"
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(book, f, ensure_ascii=False)
            os.replace(tmp, path)
            _load_book.cache_clear()
            # 译文已经在书里了，缓存文件成了重复副本，删掉省空间（index.json 留着）
            for i in merged:
                trans.drop_cache(bid, i)
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


HIDDEN_KEY = os.environ.get("HIDDEN_KEY", "zxcv")


def _hidden_ok(key: str) -> bool:
    return bool(HIDDEN_KEY) and hmac.compare_digest(HIDDEN_KEY, key or "")


@app.get("/api/hidden/check")
def hidden_check(key: str = ""):
    """搜索框里的暗号校验：只回答是不是，不返回任何内容。"""
    return {"ok": _hidden_ok(key)}


@app.get("/api/library")
def library(q: str = "", sort: str = "chars", cat: str = "", hidden: int = 0,
            x_hidden_key: str = Header("")):
    # 实时译文按磁盘清单覆盖，避免实时翻译过的书在书架上没有「译」角标
    mf = _manifest()
    if hidden:
        if not _hidden_ok(x_hidden_key):
            raise HTTPException(403, "暗号不对")
    items = [dict(x, has_cn=bool(x["has_cn"] or (m := mf.get(x["id"])) and m["n"]))
             for x in INDEX if bool(x.get("hidden")) == bool(hidden)]
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
    is_img = b.get("type") == "image"
    has_cn = False if is_img else _has_cn(b)
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
        "type": b.get("type", "text"),
        "cat": b.get("cat", "其他"),
        "lang": lang,
        "ok": b["ok"],
        "has_cn": has_cn,
        "hidden": bool(b.get("hidden")),
        # mode: en2zh = 英译中；zh2modern = 文言今译；空 = 无可切换译文
        "mode": "en2zh" if lang == "en" else ("zh2modern" if can_modern else ""),
        "can_modern": can_modern,
        "translate": bool(not is_img and trans.enabled() and (lang == "en" or can_modern)),
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
        "img": c.get("img") or "",
        "w": c.get("w", 0),
        "h": c.get("h", 0),
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
    if b.get("type") == "image":
        raise HTTPException(400, "图片书没有可翻译的正文")
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


def _drop_cn_titles(bid: str) -> None:
    if not os.path.exists(TITLES_PATH):
        return
    try:
        with open(TITLES_PATH, encoding="utf-8") as f:
            data = json.load(f) or {}
        if bid in data:
            data.pop(bid, None)
            tmp = TITLES_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, TITLES_PATH)
            _titles_state["mtime"] = -1.0
    except Exception as e:  # noqa: BLE001
        print(f"[titles] 清理 {bid} 失败: {e}", flush=True)


# ---------------------------------------------------------------- 导入书籍
# 用户上传的纯文本在服务端切章、入库，成为书库的一部分；服务端不记录任何上传者信息。
MAX_TEXT = 6_000_000      # 单本正文上限（字符）
MAX_IMPORTED = 2000       # 导入书总量上限，防止磁盘被刷爆


@app.post("/api/import")
def import_book(payload: dict = Body(...)):
    title = str(payload.get("title") or "").strip()[:120]
    author = str(payload.get("author") or "").strip()[:120]
    cat = str(payload.get("cat") or "其他")
    text = payload.get("text")
    hidden = payload.get("hidden")
    replace_id = str(payload.get("replace") or "").strip()

    if not isinstance(text, str) or len(text.strip()) < 200:
        raise HTTPException(400, "正文太短，至少 200 字")
    if len(text) > MAX_TEXT:
        raise HTTPException(413, f"正文过长，单本上限 {MAX_TEXT // 10000} 万字")

    # 覆盖更新：沿用旧书 id，保留可对齐的译文，旧正文被整体替换
    if replace_id:
        path = os.path.join(BOOKS, replace_id + ".json.gz")
        if not os.path.exists(path):
            raise HTTPException(404, "要更新的书不存在")
        book = importer.build(title, author, text, cat, hidden=bool(hidden))
        if hidden is None:
            book.pop("hidden", None)      # 未显式指定时沿用旧书的可见性
        old_n = (META.get(replace_id) or {}).get("n", 0)
        info = importer.replace(replace_id, book)
        comic.drop_media(replace_id)   # 若覆盖的是图片书，旧图一并清掉
        # 章数变了，旧的目录译名会错位，直接整条摘掉，后续打开时按需重译
        if old_n and old_n != book["n"]:
            _drop_cn_titles(replace_id)
        # 缓存按章号存，更新后可能张冠李戴，清掉最稳妥（已并入书籍的译文不受影响）
        shutil.rmtree(os.path.join(DATA, "cn_cache", replace_id), ignore_errors=True)
        reload_library()
        return {
            "ok": True,
            "updated": True,
            "id": replace_id,
            "title": book["title"],
            "author": book["author"],
            "lang": book["lang"],
            "kind": book["kind"],
            "n": book["n"],
            "chars": book["chars"],
            "kept_chapters": info["kept_chapters"],
        }

    imported = sum(1 for x in INDEX if x.get("source") == "user")
    if imported >= MAX_IMPORTED:
        raise HTTPException(507, "导入数量已达上限，请先删除部分导入书籍")

    # 同名书不默默新建一本，交给用户决定「覆盖」还是「另存」
    conflict = importer.find_conflict(title, author, bool(hidden))
    if conflict and not payload.get("allow_duplicate"):
        raise HTTPException(409, detail={
            "msg": f"已存在同名书籍《{conflict['title']}》",
            "conflict": {
                "id": conflict["id"],
                "title": conflict["title"],
                "author": conflict.get("author", ""),
                "n": conflict.get("n", 0),
                "hidden": bool(conflict.get("hidden")),
            },
        })

    book = importer.build(title, author, text, cat, hidden=bool(hidden))
    importer.save(book)
    reload_library()
    return {
        "ok": True,
        "id": book["id"],
        "title": book["title"],
        "author": book["author"],
        "lang": book["lang"],
        "kind": book["kind"],
        "n": book["n"],
        "chars": book["chars"],
        "hidden": bool(book.get("hidden")),
    }


# ---------------------------------------------------------------- 导入图片（漫画）
# 一张图一页，前端按批提交（每批 ≤60 张），避免一次几百张把网关拖超时。
MAX_BATCH = 60

# 批次幂等：同一批因超时重发时直接回放上次结果，不会重复追加
_BATCH_FILE = os.path.join(DATA, "batches.json")
_batch_lock = threading.Lock()
_BATCH_TTL = 24 * 3600
_BATCH_MAX = 3000


def _batch_get(token: str):
    if not token:
        return None
    with _batch_lock:
        try:
            with open(_BATCH_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return None
        hit = d.get(token)
        if not hit or time.time() - hit.get("t", 0) > _BATCH_TTL:
            return None
        res = hit.get("r") or {}
        # 会话已被回收 / 已提交，回放旧回执只会把客户端指向一个死会话
        if res.get("staging") and not comic.stage_exists(res["staging"]):
            return None
        return res


def _batch_put(token: str, res: dict) -> None:
    if not token:
        return
    with _batch_lock:
        try:
            with open(_BATCH_FILE, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            d = {}
        now = time.time()
        d = {k: v for k, v in d.items() if now - v.get("t", 0) <= _BATCH_TTL}
        d[token] = {"t": now, "r": res}
        if len(d) > _BATCH_MAX:
            for k in sorted(d, key=lambda x: d[x]["t"])[:len(d) - _BATCH_MAX]:
                d.pop(k, None)
        tmp = _BATCH_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(tmp, _BATCH_FILE)
        except OSError:
            pass


def _stage_err(e: "comic.StageError"):
    return HTTPException(e.status, detail={"msg": e.msg, **e.extra})


@app.post("/api/import/images")
async def import_images(
    files: list[UploadFile] = File(...),
    title: str = Form(""),
    author: str = Form(""),
    cat: str = Form("其他"),
    hidden: str = Form(""),
    replace: str = Form(""),
    append: str = Form(""),
    allow_duplicate: str = Form(""),
    stage: str = Form(""),
    target: str = Form(""),
    expect: str = Form(""),
    batch: str = Form(""),
):
    cached = _batch_get(batch)
    if cached:
        return cached

    if not files:
        raise HTTPException(400, "没有收到图片")
    if len(files) > MAX_BATCH:
        raise HTTPException(413, f"单次最多 {MAX_BATCH} 张，请分批上传")

    items = []
    total = 0
    for f in files:
        name = f.filename or "page.jpg"
        if not comic.is_image(name):
            continue
        raw = await f.read()
        total += len(raw)
        if total > 120 * 1024 * 1024:
            raise HTTPException(413, "这一批图片超过 120MB，请分批上传")
        if raw:
            items.append((name, raw))
    if not items:
        raise HTTPException(400, "没有可用的图片（支持 jpg / png / webp / gif / bmp / avif）")
    items.sort(key=lambda x: comic.natural_key(x[0]))

    try:
        want = int(expect or 0)
    except ValueError:
        want = 0

    # ① 开一个暂存会话：覆盖更新的中间态，旧书一个字节都不动
    if stage:
        meta = comic.stage_new(title, author, cat, bool(hidden), target, want)
        try:
            info = comic.stage_add(meta["id"], items)
        except comic.StageError as e:
            comic.stage_drop(meta["id"])
            raise _stage_err(e)
        if not info["added"]:
            comic.stage_drop(meta["id"])
            raise HTTPException(400, detail={"msg": "这些图片都无法解析",
                                             "errors": info["errors"]})
        res = {"ok": True, "staging": meta["id"], "target": meta["target"],
               "expect": want, **info}
        _batch_put(batch, res)
        return res

    # ② 追加：既可能是暂存会话的后续批次，也可能是普通图片书的续传
    if append:
        if comic.stage_exists(append):
            try:
                info = comic.stage_add(append, items)
                st = comic.stage_info(append)
            except comic.StageError as e:
                raise _stage_err(e)
            res = {"ok": True, "staging": append, "appended": True, **st, **info}
            _batch_put(batch, res)
            return res
        b = comic.load(append)
        if not b or b.get("type") != "image":
            raise HTTPException(404, "要追加的书不存在")
        if len(b["chapters"]) + len(items) > comic.MAX_PAGES:
            raise HTTPException(413, f"单本上限 {comic.MAX_PAGES} 页")
        info = comic.add_pages(b, items)
        comic.update(append, b)
        reload_library()
        res = {"ok": True, "id": append, "n": b["n"], "appended": True, **info}
        _batch_put(batch, res)
        return res

    if len(items) > comic.MAX_PAGES:
        raise HTTPException(413, f"单本上限 {comic.MAX_PAGES} 页")

    title = (title or "").strip()[:120]

    # ③ 覆盖更新（单请求兼容路径）：先落暂存区，校验通过才切换，失败不动旧书
    if replace:
        if not comic.load(replace):
            raise HTTPException(404, "要更新的书不存在")
        meta = comic.stage_new(title, author, cat, bool(hidden), replace, len(items))
        try:
            info = comic.stage_add(meta["id"], items)
            if not info["added"]:
                comic.stage_drop(meta["id"])
                raise HTTPException(400, detail={"msg": "这些图片都无法解析",
                                                 "errors": info["errors"]})
            res = comic.stage_commit(meta["id"], replace)
        except comic.StageError as e:
            comic.stage_drop(meta["id"])
            raise _stage_err(e)
        except HTTPException:
            raise
        except Exception:
            comic.stage_drop(meta["id"])
            raise
        reload_library()
        res.update(info)
        _batch_put(batch, res)
        return res

    imported = sum(1 for x in INDEX if x.get("source") == "user")
    if imported >= MAX_IMPORTED:
        raise HTTPException(507, "导入数量已达上限，请先删除部分导入书籍")

    conflict = importer.find_conflict(title, author, bool(hidden)) if title else None
    if conflict and not allow_duplicate:
        raise HTTPException(409, detail={
            "msg": f"已存在同名书籍《{conflict['title']}》",
            "conflict": {
                "id": conflict["id"],
                "title": conflict["title"],
                "author": conflict.get("author", ""),
                "n": conflict.get("n", 0),
                "hidden": bool(conflict.get("hidden")),
                "count": conflict.get("_same_title", 1),
            },
        })

    book = comic.new_book(title, author, cat, bool(hidden))
    info = comic.add_pages(book, items)
    if not info["added"]:
        comic.drop_media(book["id"])
        raise HTTPException(400, detail={"msg": "这些图片都无法解析", "errors": info["errors"]})
    comic.update(book["id"], book)
    reload_library()
    res = {"ok": True, "id": book["id"], "title": book["title"], "author": book["author"],
           "n": book["n"], "hidden": bool(book["hidden"]), **info}
    _batch_put(batch, res)
    return res


@app.post("/api/import/images/commit")
def commit_images(stage: str = Form(...), target: str = Form("")):
    """把暂存会话整体切换成正式书；页数不齐、文件缺失都会拒绝，旧书不受影响。"""
    try:
        res = comic.stage_commit(stage, target)
    except comic.StageError as e:
        raise _stage_err(e)
    if res.get("was_text"):
        # 文本书被图片覆盖：旧译文缓存与目录译名都不再适用
        shutil.rmtree(os.path.join(DATA, "cn_cache", res["id"]), ignore_errors=True)
        _drop_cn_titles(res["id"])
    reload_library()
    return res


@app.get("/api/import/images/stage/{sid}")
def stage_state(sid: str):
    try:
        return comic.stage_info(sid)
    except comic.StageError as e:
        raise _stage_err(e)


@app.delete("/api/import/images/stage/{sid}")
def stage_cancel(sid: str):
    comic.stage_drop(sid)
    return {"ok": True}


def _admin(token: str) -> None:
    """删除操作校验：必须配置 ADMIN_TOKEN，且口令一致。"""
    real = os.environ.get("ADMIN_TOKEN", "")
    if not real:
        raise HTTPException(403, "未开启删除功能（启动时设置 ADMIN_TOKEN 环境变量）")
    if not hmac.compare_digest(real, token or ""):
        raise HTTPException(403, "口令不正确")


@app.delete("/api/book/{bid}")
def delete_book(bid: str, x_admin_token: str = Header("")):
    """彻底删除任意一本书（内置书与导入书一视同仁），不可恢复。

    正文文件、图片页、章节译文缓存、目录译名全部清掉，
    书库索引同步摘除。删除前请自行留档。
    """
    _admin(x_admin_token)
    # 与「翻译完成回写整本」互斥：否则回写线程可能在文件删掉后又写回来
    with _persist_lock:
        if not importer.delete(bid):
            raise HTTPException(404, "书不存在")
    comic.drop_media(bid)
    shutil.rmtree(os.path.join(DATA, "cn_cache", bid), ignore_errors=True)
    _drop_cn_titles(bid)
    reload_library()
    return {"ok": True, "id": bid, "deleted": True}


@app.get("/api/stats")
def stats(hidden: int = 0, x_hidden_key: str = Header("")):
    if hidden and not _hidden_ok(x_hidden_key):
        raise HTTPException(403, "暗号不对")
    pool = [x for x in INDEX if bool(x.get("hidden")) == bool(hidden)]
    cats = {}
    for x in pool:
        cats[x["cat"]] = cats.get(x["cat"], 0) + 1
    return {
        "books": len(pool),
        "complete": sum(1 for x in pool if x["ok"]),
        "chars": sum(x["chars"] for x in pool if x["lang"] == "zh"),
        "words": sum(x["words"] for x in pool if x["lang"] == "en"),
        "chinese": sum(1 for x in pool if x["lang"] == "zh" and x.get("type") != "image"),
        "comic": sum(1 for x in pool if x.get("type") == "image"),
        "western": sum(1 for x in pool if x["lang"] == "en"),
        "imported": sum(1 for x in pool if x.get("source") == "user"),
        "cats": [{"name": c, "n": cats[c]} for c in CATS if cats.get(c)],
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
os.makedirs(MEDIA, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")
