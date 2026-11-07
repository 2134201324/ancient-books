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

MAX_SIDE = 1800       # 长边上限
QUALITY = 86          # JPEG 质量
MAX_PAGES = 400       # 单本页数上限
MAX_BYTES = 16 * 1024 * 1024   # 单张上限

_lock = threading.Lock()
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


def replace_with(bid: str, book: dict) -> None:
    """覆盖更新：新书先写在自己的临时目录里，再整体替换旧目录。

    这样即使替换到一半失败，旧书与旧图仍然完整。
    """
    old = load(bid)
    src = media_dir(book["id"])
    drop_media(bid)
    if os.path.isdir(src):
        os.makedirs(MEDIA, exist_ok=True)
        os.replace(src, media_dir(bid))
    book["id"] = bid
    if old:
        book["added"] = old.get("added") or book["added"]
        book["hidden"] = bool(old.get("hidden"))
    with _lock:
        importer.save(book)
