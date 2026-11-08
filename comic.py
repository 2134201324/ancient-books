"""图片书（漫画）：把上传的图片压缩后逐页入库。

设计要点
- 一张图 = 一页 = 一个章节，沿用现有的翻页 / 目录 / 进度逻辑，前端不用另起一套。
- 页序按文件名自然排序（1、2、10 而不是 1、10、2），浏览器多选与文件夹上传都适用。
- 统一转 JPEG（长边 ≤ 1800，质量 86）：手机拍的 4MB 图通常压到 200–500KB，
  几百页也就几十兆，阅读时也不必下载原图。
- 图片存 data/media/<书号>/<序号>.jpg，书籍文件里只记文件名，gz 依然很小。
- 分批上传：一次请求处理一批（默认 ≤ 60 张），前端循环提交，避免网关超时。
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import shutil
import threading
import time

from PIL import Image, ImageOps

import importer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BOOKS = os.path.join(DATA, "books")
MEDIA = os.path.join(DATA, "media")
STAGING = os.path.join(DATA, "staging")

MAX_SIDE = 1800       # 长边上限
QUALITY = 86          # JPEG 质量
MAX_PAGES = 400       # 单本页数上限
MAX_BYTES = 16 * 1024 * 1024   # 单张上限

STAGE_TTL = 24 * 3600  # 暂存会话保留 24 小时，过期自动回收

_lock = threading.Lock()
_stage_lock = threading.Lock()
_gc_at = [0.0]
_EXT = re.compile(r"\.(jpe?g|png|webp|gif|bmp|avif)$", re.I)


def is_image(name: str) -> bool:
    return bool(_EXT.search(name or ""))


def natural_key(name: str):
    """文件名自然排序：IMG_2 排在 IMG_10 前面。"""
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r"(\d+)", os.path.basename(name or ""))]


def shrink(raw: bytes) -> tuple[bytes, int, int]:
    """压缩成 JPEG。透明图铺白底，带 EXIF 方向的先摆正。"""
    im = Image.open(io.BytesIO(raw))
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), im.size[0], im.size[1]


def media_dir(bid: str) -> str:
    return os.path.join(MEDIA, bid)


def new_book(title: str, author: str, cat: str, hidden: bool) -> dict:
    cat = cat if cat in importer.CATS else "其他"
    bid = importer.new_id()
    title = (title or "").strip()[:120] or f"漫画 {time.strftime('%m%d-%H%M')}"
    return {
        "id": bid,
        "title": title,
        "author": (author or "佚名").strip()[:120],
        "lang": "zh",
        "cat": cat,
        "kind": "漫画",
        "type": "image",
        "chars": 0,
        "words": 0,
        "n": 0,
        "ok": True,
        "has_cn": False,
        "wen": 0,
        "source": "user",
        "hidden": bool(hidden),
        "added": int(time.time()),
        "chapters": [],
    }


def add_pages(book: dict, items: list[tuple[str, bytes]]) -> dict:
    """往 book 里追加一批图片。items = [(文件名, 原始字节)]。

    返回 {added, skipped, errors}；已写入的页会立刻落盘，中断也能保住前面的部分。
    """
    d = media_dir(book["id"])
    os.makedirs(d, exist_ok=True)
    added, skipped, errors = 0, 0, []

    for name, raw in items:
        if len(book["chapters"]) >= MAX_PAGES:
            skipped += 1
            continue
        if len(raw) > MAX_BYTES:
            skipped += 1
            errors.append(f"{name}：超过 {MAX_BYTES // 1024 // 1024} MB")
            continue
        try:
            data, w, h = shrink(raw)
        except Exception as e:  # noqa: BLE001
            skipped += 1
            errors.append(f"{name}：不是可识别的图片（{type(e).__name__}）")
            continue
        idx = len(book["chapters"]) + 1
        fn = f"{idx:04d}.jpg"
        with open(os.path.join(d, fn), "wb") as f:
            f.write(data)
        book["chapters"].append({
            "title": f"第 {idx} 页",
            "text": "",
            "img": fn,
            "src": os.path.basename(name)[:120],
            "w": w,
            "h": h,
        })
        added += 1

    book["n"] = len(book["chapters"])
    return {"added": added, "skipped": skipped, "errors": errors[:8]}


def drop_media(bid: str) -> None:
    shutil.rmtree(media_dir(bid), ignore_errors=True)


def load(bid: str) -> dict | None:
    path = os.path.join(BOOKS, bid + ".json.gz")
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def update(bid: str, book: dict) -> None:
    """把内存里的书写回磁盘（追加页之后调用）。"""
    book["n"] = len(book["chapters"])
    with _lock:
        importer.save(book)


# ---------------------------------------------------------------- 更新暂存区
class StageError(Exception):
    """暂存 / 提交阶段的业务错误，带 HTTP 状态码与可读原因。"""

    def __init__(self, status: int, msg: str, **extra):
        self.status = status
        self.msg = msg
        self.extra = extra
        super().__init__(msg)


def stage_dir(sid: str) -> str:
    return os.path.join(STAGING, sid)


def _stage_meta_path(sid: str) -> str:
    return os.path.join(STAGING, sid + ".json")


def stage_load(sid: str) -> dict | None:
    p = _stage_meta_path(sid)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _stage_save(meta: dict) -> None:
    os.makedirs(STAGING, exist_ok=True)
    p = _stage_meta_path(meta["id"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, p)


def stage_exists(sid: str) -> bool:
    return bool(sid) and os.path.exists(_stage_meta_path(sid))


def stage_gc() -> int:
    """回收过期会话，避免用户中途放弃后把磁盘一直占着。"""
    now = time.time()
    if now - _gc_at[0] < 3600:      # 一小时最多扫一次
        return 0
    _gc_at[0] = now
    if not os.path.isdir(STAGING):
        return 0
    killed = 0
    for name in os.listdir(STAGING):
        p = os.path.join(STAGING, name)
        try:
            if now - os.path.getmtime(p) < STAGE_TTL:
                continue
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            killed += 1
        except OSError:
            continue
    return killed


def stage_new(title: str, author: str, cat: str, hidden: bool,
              target: str = "", expect: int = 0) -> dict:
    """开一个暂存会话。target 非空表示这次是覆盖更新，旧书暂不受影响。"""
    stage_gc()
    sid = importer.new_id()
    meta = {
        "id": sid,
        "target": (target or "").strip(),
        "title": (title or "").strip()[:120],
        "author": (author or "").strip()[:120],
        "cat": cat if cat in importer.CATS else "",   # 空=沿用旧书的分类
        "hidden": bool(hidden),
        "expect": int(expect or 0),
        "created": int(time.time()),
        "pages": [],
    }
    os.makedirs(stage_dir(sid), exist_ok=True)
    _stage_save(meta)
    return meta


def stage_add(sid: str, items: list[tuple[str, bytes]]) -> dict:
    """往暂存会话里加一批图，返回 {added, skipped, errors, n}。"""
    with _stage_lock:
        meta = stage_load(sid)
        if not meta:
            raise StageError(404, "上传会话已失效，请重新导入")
        d = stage_dir(sid)
        os.makedirs(d, exist_ok=True)
        added, skipped, errors = 0, 0, []
        for name, raw in items:
            if len(meta["pages"]) >= MAX_PAGES:
                skipped += 1
                continue
            if len(raw) > MAX_BYTES:
                skipped += 1
                errors.append(f"{name}：超过 {MAX_BYTES // 1024 // 1024} MB")
                continue
            try:
                data, w, h = shrink(raw)
            except Exception as e:  # noqa: BLE001
                skipped += 1
                errors.append(f"{name}：不是可识别的图片（{type(e).__name__}）")
                continue
            idx = len(meta["pages"]) + 1
            fn = f"{idx:04d}.jpg"
            with open(os.path.join(d, fn), "wb") as f:
                f.write(data)
            meta["pages"].append({
                "img": fn,
                "src": os.path.basename(name)[:120],
                "w": w, "h": h,
            })
            added += 1
        _stage_save(meta)
        return {"added": added, "skipped": skipped,
                "errors": errors[:8], "n": len(meta["pages"])}


def stage_info(sid: str) -> dict:
    meta = stage_load(sid)
    if not meta:
        raise StageError(404, "上传会话已失效，请重新导入")
    return {"staging": sid, "n": len(meta["pages"]),
            "expect": meta.get("expect", 0), "target": meta.get("target", "")}


def stage_drop(sid: str) -> None:
    shutil.rmtree(stage_dir(sid), ignore_errors=True)
    try:
        os.remove(_stage_meta_path(sid))
    except OSError:
        pass


def _build_book(meta: dict, old: dict | None, bid: str) -> dict:
    title = meta.get("title") or (old or {}).get("title") or ""
    if not title:
        title = f"漫画 {time.strftime('%m%d-%H%M')}"
    author = meta.get("author") or (old or {}).get("author") or "佚名"
    cat = meta.get("cat") or (old or {}).get("cat") or "其他"
    if cat not in importer.CATS:
        cat = "其他"
    pages = meta["pages"]
    return {
        "id": bid,
        "title": title[:120],
        "author": author[:120],
        "lang": "zh",
        "cat": cat,
        "kind": "漫画",
        "type": "image",
        "chars": 0,
        "words": 0,
        "n": len(pages),
        "ok": True,
        "has_cn": False,
        "wen": 0,
        "source": "user",
        # 覆盖时沿用旧书的可见性，避免一次更新把公开书藏起来（或反之）
        "hidden": bool(old.get("hidden")) if old else bool(meta.get("hidden")),
        "added": int((old or {}).get("added") or time.time()),
        "chapters": [
            {"title": f"第 {i} 页", "text": "", "img": p["img"],
             "src": p.get("src", ""), "w": p.get("w"), "h": p.get("h")}
            for i, p in enumerate(pages, 1)
        ],
    }


def stage_commit(sid: str, target: str = "") -> dict:
    """把暂存内容整体切换成正式书。

    切换前做四项探测：页数是否到齐、每页文件是否真的存在、磁盘余量是否够、
    目标书是否还在。任何一项不过就拒绝提交，旧书一个字节都不动。
    """
    with _stage_lock:
        meta = stage_load(sid)
        if not meta:
            raise StageError(404, "上传会话已失效，请重新导入")
        target = (target or meta.get("target") or "").strip()
        pages = meta["pages"]
        n = len(pages)
        expect = int(meta.get("expect") or 0)

        if expect and n != expect:
            raise StageError(
                409,
                f"只收到 {n} / {expect} 页，还差 {expect - n} 页，已拒绝更新（旧书未改动）",
                n=n, expect=expect, missing=expect - n,
            )
        if n == 0:
            raise StageError(400, "没有可入库的页")

        d = stage_dir(sid)
        broken = [p["img"] for p in pages
                  if not os.path.isfile(os.path.join(d, p["img"]))
                  or os.path.getsize(os.path.join(d, p["img"])) == 0]
        if broken:
            raise StageError(409, f"{len(broken)} 页图片缺失或为空（如 {broken[0]}），已拒绝更新",
                             n=n, broken=broken[:8])

        size = sum(os.path.getsize(os.path.join(d, p["img"])) for p in pages)
        os.makedirs(MEDIA, exist_ok=True)
        free = shutil.disk_usage(MEDIA).free
        if size + 8 * 1024 * 1024 > free:
            raise StageError(507, "磁盘剩余空间不足，已拒绝更新（旧书未改动）")

        old = load(target) if target else None
        if target and not old:
            target = ""          # 目标书已被删掉，按新建处理
        bid = target or sid
        book = _build_book(meta, old, bid)

        new_dir = media_dir(bid) + ".new"
        old_dir = media_dir(bid) + ".old"
        shutil.rmtree(new_dir, ignore_errors=True)
        os.replace(d, new_dir)                    # 暂存 → <书号>.new
        had_old = os.path.isdir(media_dir(bid))
        if had_old:
            shutil.rmtree(old_dir, ignore_errors=True)
            os.replace(media_dir(bid), old_dir)   # 旧图 → <书号>.old
        os.replace(new_dir, media_dir(bid))       # 新图 → 正式目录
        try:
            importer.save(book)
        except Exception:
            # 写书失败：目录原样退回，旧书继续可用
            try:
                os.replace(media_dir(bid), d)
                if had_old:
                    os.replace(old_dir, media_dir(bid))
            except OSError:
                pass
            raise
        if had_old:
            shutil.rmtree(old_dir, ignore_errors=True)
        try:
            os.remove(_stage_meta_path(sid))
        except OSError:
            pass
        return {"ok": True, "updated": bool(old), "id": bid, "n": n,
                "title": book["title"], "author": book["author"],
                "hidden": book["hidden"], "bytes": size,
                # 原来那本是文本书：它的译文与目录译名都该作废
                "was_text": bool(old and old.get("type") != "image")}

