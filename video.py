"""视频书：分片上传、探测、封面与播放。

设计要点
- 上传走 8MB 分片，落在 data/uploads/<令牌>/<序号>.part，断开后重选同一个
  文件即可续传（令牌由「文件名+大小+修改时间」算哈希得到，不依赖客户端记忆）。
- 合并后写入 data/media/<书号>/0001.mp4，交给 /media 的 StaticFiles 提供
  Range 响应，播放器能直接拖进度条，服务端不用把整个文件读进内存。
- 有 ffmpeg 时抽一张封面、把 mov/mkv 之类重封装成 mp4（只转容器不解码，
  几秒钟）；没有 ffmpeg 也能入库，只是缺封面、个别格式浏览器不认。
- 视频书沿用「一章一个文件」的结构：单集就是 1 章，多集按集号排。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time

import importer

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
BOOKS = os.path.join(DATA, "books")
MEDIA = os.path.join(DATA, "media")
UPLOADS = os.path.join(DATA, "uploads")

CHUNK = 8 * 1024 * 1024            # 单片 8MB，手机网络断一次也只重传这一片
MAX_BYTES = 3 * 1024 * 1024 * 1024  # 单文件 3GB
MAX_FILES = 400                    # 单本集数上限
UPLOAD_TTL = 48 * 3600             # 未完成的上传保留两天

VIDEO_EXT = (".mp4", ".m4v", ".webm", ".ogv", ".mov", ".mkv", ".avi", ".ts", ".flv")
PLAYABLE_EXT = (".mp4", ".m4v", ".webm", ".ogv")

_lock = threading.Lock()

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or ""
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or ""


class VideoError(Exception):
    """带 HTTP 状态码的业务错误。"""

    def __init__(self, status: int, msg: str):
        self.status = status
        self.msg = msg
        super().__init__(msg)


# ---------------------------------------------------------------- 工具
def is_video(name: str, ctype: str = "") -> bool:
    return name.lower().endswith(VIDEO_EXT) or (ctype or "").startswith("video/")


def _updir(uid: str) -> str:
    return os.path.join(UPLOADS, uid)


def _meta_path(uid: str) -> str:
    return os.path.join(_updir(uid), "meta.json")


def _read_meta(uid: str) -> dict | None:
    p = _meta_path(uid)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_meta(uid: str, meta: dict) -> None:
    os.makedirs(_updir(uid), exist_ok=True)
    tmp = _meta_path(uid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, _meta_path(uid))


def fingerprint(name: str, size: int, mtime: float) -> str:
    """文件名+大小+修改时间，够区分不同视频，也不用读文件内容。"""
    raw = f"{name}|{int(size)}|{int(mtime or 0)}".encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def gc() -> int:
    """回收两天没动静的上传会话（含半个大文件），返回清掉的目录数。"""
    if not os.path.isdir(UPLOADS):
        return 0
    now, n = time.time(), 0
    for uid in list(os.listdir(UPLOADS)):
        d = _updir(uid)
        if not os.path.isdir(d):
            continue
        try:
            mt = max(os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d)) if os.listdir(d) else os.path.getmtime(d)
        except OSError:
            mt = os.path.getmtime(d)
        if now - mt > UPLOAD_TTL:
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n


def disk_free() -> int:
    return shutil.disk_usage(DATA).free


# ---------------------------------------------------------------- 分片上传
def begin(fp: str, name: str, size: int) -> dict:
    """开一个上传会话；同一个文件重选时沿用旧会话，已收的分片不重传。"""
    if size <= 0:
        raise VideoError(400, "文件是空的")
    if size > MAX_BYTES:
        raise VideoError(413, f"单个视频最大 {MAX_BYTES // (1024**3)} GB")
    if disk_free() < size + 200 * 1024 * 1024:
        raise VideoError(507, "磁盘剩余空间不足，无法接收这个视频")
    gc()
    uid = hashlib.sha1(fp.encode()).hexdigest()[:16] if fp else importer.new_id()
    meta = _read_meta(uid)
    if not meta:
        meta = {"id": uid, "name": (name or "")[:200], "size": int(size),
                "chunk": CHUNK, "total": (int(size) + CHUNK - 1) // CHUNK,
                "received": [], "created": int(time.time()), "fp": fp}
        _write_meta(uid, meta)
        os.makedirs(_updir(uid), exist_ok=True)
    elif meta.get("size") != int(size):
        # 同名同大小的不同文件（换过内容）→ 换一个会话，避免拼出错文件
        shutil.rmtree(_updir(uid), ignore_errors=True)
        meta.update({"received": [], "size": int(size),
                     "total": (int(size) + CHUNK - 1) // CHUNK, "created": int(time.time())})
        _write_meta(uid, meta)
    got = []
    for i in range(meta["total"]):
        p = os.path.join(_updir(uid), f"{i}.part")
        if os.path.exists(p) and os.path.getsize(p) > 0:
            got.append(i)
    return {"upload": uid, "chunk": meta["chunk"], "total": meta["total"],
            "received": got, "size": meta["size"]}


def put_chunk(uid: str, index: int, blob: bytes) -> dict:
    meta = _read_meta(uid)
    if not meta:
        raise VideoError(404, "上传会话不存在或已过期，请重新选择文件")
    total = int(meta.get("total") or 0)
    if index < 0 or index >= total:
        raise VideoError(400, "分片序号越界")
    if not blob:
        raise VideoError(400, "分片是空的")
    d = _updir(uid)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{index}.part")
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, p)
    with _lock:
        m = _read_meta(uid) or meta
        rec = set(m.get("received") or [])
        rec.add(index)
        m["received"] = sorted(rec)
        m["at"] = int(time.time())
        _write_meta(uid, m)
        return {"upload": uid, "received": len(m["received"]), "total": total}


# ---------------------------------------------------------------- 探测 / 封面
def probe(path: str) -> dict:
    """读时长与分辨率；没有 ffprobe 就返回空，一切照常入库。"""
    if not FFPROBE:
        return {}
    try:
        r = subprocess.run(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return {}
        j = json.loads(r.stdout or "{}")
        st = (j.get("streams") or [{}])[0]
        dur = float((j.get("format") or {}).get("duration") or 0)
        return {"dur": round(dur), "w": int(st.get("width") or 0), "h": int(st.get("height") or 0)}
    except Exception:
        return {}


def make_poster(video: str, out: str) -> bool:
    """抽第 3 秒的一帧当封面；片子比 3 秒短就抽第一帧。"""
    if not FFMPEG:
        return False
    for ss in ("00:00:03", "00:00:00"):
        try:
            r = subprocess.run(
                [FFMPEG, "-y", "-ss", ss, "-i", video, "-frames:v", "1",
                 "-vf", "scale='min(720,iw)':-2", "-q:v", "4", out],
                capture_output=True, timeout=60,
            )
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                return True
        except Exception:
            continue
    return False


def remux(src: str, dst: str) -> str:
    """把不保证能播的容器转成 mp4（只换壳不重编码）。返回最终文件路径。"""
    ext = os.path.splitext(src)[1].lower()
    if ext in PLAYABLE_EXT or not FFMPEG:
        return src
    try:
        r = subprocess.run(
            [FFMPEG, "-y", "-i", src, "-c", "copy", "-movflags", "+faststart",
             "-f", "mp4", dst],
            capture_output=True, timeout=600,
        )
        if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            return dst
    except Exception:
        pass
    return src


# ---------------------------------------------------------------- 入库
def _safe_title(name: str) -> str:
    t = os.path.splitext(os.path.basename(name or ""))[0]
    t = re.sub(r"[_]+", " ", t).strip()
    return t[:120]


def finish(uid: str, title: str = "", author: str = "", cat: str = "其他",
           hidden: bool = False, append: str = "") -> dict:
    """把已收齐的分片合并成一个视频文件，登记成书（或追加为新一集）。"""
    meta = _read_meta(uid)
    if not meta:
        raise VideoError(404, "上传会话不存在或已过期，请重新选择文件")
    total = int(meta.get("total") or 0)
    rec = set(meta.get("received") or [])
    missing = [i for i in range(total) if i not in rec]
    if missing:
        raise VideoError(409, f"还差 {len(missing)} 个分片（第 {missing[0] + 1} 片起），请继续上传")

    d = _updir(uid)
    size = sum(os.path.getsize(os.path.join(d, f"{i}.part")) for i in range(total))
    if size != int(meta["size"]):
        raise VideoError(409, f"分片总大小不符（收到 {size}，应为 {meta['size']}），请重新上传")
    if disk_free() < 200 * 1024 * 1024:
        raise VideoError(507, "磁盘剩余空间不足")

    old = None
    if append:
        old = _load(append)
        if not old or old.get("type") != "video":
            raise VideoError(404, "要追加的视频书不存在")
        if len(old.get("chapters") or []) >= MAX_FILES:
            raise VideoError(413, f"单本最多 {MAX_FILES} 集")

    bid = append or importer.new_id()
    mdir = os.path.join(MEDIA, bid)
    os.makedirs(mdir, exist_ok=True)
    seq = len(old["chapters"]) + 1 if old else 1
    ext = os.path.splitext(meta["name"])[1].lower()
    ext = ".mp4" if ext not in VIDEO_EXT else ext
    target = os.path.join(mdir, f"{seq:04d}{ext}")

    # 顺序拼接：逐片读、逐片写，内存里始终只有 8MB
    tmp = target + ".part"
    try:
        with open(tmp, "wb") as out:
            for i in range(total):
                with open(os.path.join(d, f"{i}.part"), "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        os.replace(tmp, target)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise VideoError(507, f"写入失败：{e}")

    # 换壳：mov/mkv/avi 之类转成 mp4，播放器才认；失败就保留原文件
    if ext not in PLAYABLE_EXT:
        fixed = remux(target, os.path.join(mdir, f"{seq:04d}.mp4"))
        if fixed != target:
            try:
                os.remove(target)
            except OSError:
                pass
            target = fixed

    info = probe(target)
    poster = os.path.join(mdir, "poster.jpg") if seq == 1 else ""
    if poster:
        make_poster(target, poster)

    name = os.path.basename(target)
    rel = os.path.relpath(target, mdir).replace(os.sep, "/")
    ch = {"title": f"第 {seq} 集" if (old or False) or seq > 1 else _safe_title(meta["name"]) or "视频",
          "text": "", "file": rel, "dur": info.get("dur", 0),
          "w": info.get("w", 0), "h": info.get("h", 0), "size": os.path.getsize(target)}

    if old:
        # 首集原本叫书名，加第二集时统一成「第 1 集」，目录才整齐
        if len(old["chapters"]) == 1 and old["chapters"][0]["title"] == old["title"]:
            old["chapters"][0]["title"] = "第 1 集"
        old["chapters"].append(ch)
        old["n"] = len(old["chapters"])
        old["size"] = sum(int(c.get("size") or 0) for c in old["chapters"])
        old["dur"] = sum(int(c.get("dur") or 0) for c in old["chapters"])
        if seq == 1:
            old["has_poster"] = bool(poster and os.path.exists(poster))
        book = old
    else:
        t = (title or "").strip()[:120] or _safe_title(meta["name"]) or "视频"
        book = {
            "id": bid,
            "title": t,
            "author": (author or "佚名").strip()[:120],
            "lang": "zh",
            "cat": cat if cat in importer.CATS else "其他",
            "kind": "视频",
            "type": "video",
            "chars": 0,
            "words": 0,
            "n": 1,
            "ok": True,
            "has_cn": False,
            "wen": 0,
            "source": "user",
            "hidden": bool(hidden),
            "added": int(time.time()),
            "size": int(os.path.getsize(target)),
            "dur": int(ch["dur"] or 0),
            "has_poster": bool(poster and os.path.exists(poster)),
            "chapters": [ch],
        }

    with _lock:
        importer.save(book)
    shutil.rmtree(d, ignore_errors=True)   # 分片已合并，尽快把临时空间还回去
    return {"ok": True, "id": bid, "n": book["n"], "title": book["title"],
            "dur": ch["dur"], "w": ch["w"], "h": ch["h"],
            "size": ch["size"], "file": name, "poster": bool(book.get("has_poster"))}


def _load(bid: str) -> dict | None:
    p = os.path.join(BOOKS, bid + ".json.gz")
    if not os.path.exists(p):
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def drop(bid: str) -> None:
    shutil.rmtree(os.path.join(MEDIA, bid), ignore_errors=True)


def status(uid: str) -> dict | None:
    """查一个上传会话收到哪里了，供断点续传用。"""
    meta = _read_meta(uid)
    if not meta:
        return None
    total = int(meta.get("total") or 0)
    d = _updir(uid)
    got = [i for i in range(total)
           if os.path.exists(os.path.join(d, f"{i}.part"))
           and os.path.getsize(os.path.join(d, f"{i}.part")) > 0]
    return {"upload": uid, "name": meta.get("name", ""), "size": meta.get("size", 0),
            "chunk": meta.get("chunk", CHUNK), "total": total,
            "received": got, "done": len(got) == total and total > 0}
