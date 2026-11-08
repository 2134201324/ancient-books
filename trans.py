"""实时翻译通道：把英文书籍按章送 OpenAI 兼容接口，返回与原文对齐的中文。

设计要点
- 只依赖 base_url / api_key 两个信息；模型名留空时自动向 /models 探测。
- 按段落分块，逐块请求，块内段落严格 1:1 对应，避免中英错位。
- 每块译完即落盘（data/cn_cache/<book>/<ch>.json），中断可续、重复读免费。
- 密钥只从环境变量或 .secrets/translate.json 读取，永不出现在前端或接口响应里。

环境变量（优先）：
    TRANSLATE_BASE_URL / OPENAI_BASE_URL   接口地址，如 https://api.openai.com/v1
    TRANSLATE_API_KEY  / OPENAI_API_KEY    密钥
    TRANSLATE_MODEL                        模型名（可省略，自动探测）
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator, Iterable

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
SECRETS = [
    os.path.join(BASE, ".secrets", "translate.json"),
    os.path.join(BASE, "data", "translate.json"),
]
SECRET = SECRETS[0]
CACHE_DIR = os.path.join(BASE, "data", "cn_cache")

MAX_BLOCK_CHARS = 2600      # 单次请求的英文体量上限
MAX_BLOCK_PARAS = 14
HARD_PARA_LIMIT = 7000      # 单段超长时的硬上限
TIMEOUT = 180
WORKERS = 3                 # 同时请求的块数

SYSTEM = (
    "你是资深文学与学术译者，负责把英文典籍译成简体中文。严格遵守：\n"
    "1. 只输出一个 JSON 对象，形如 {\"title\":\"中文章节标题\",\"paras\":[\"第一段\",\"第二段\"]}；\n"
    "2. paras 的条数必须与输入段落数完全相同，逐段一一对应，不得合并、拆分、增删、遗漏；\n"
    "3. 不要输出任何解释、前言、注释或 markdown 代码块围栏；\n"
    "4. 人名、地名、书名与术语沿用汉语通行译名；哲学与科学概念要准确，不意译成近义词；\n"
    "5. 译文为规范书面汉语，保留原文的语气与论证层次，不口语化、不添油加醋；\n"
    "6. 原文中的斜体、脚注标记等排版符号可以略去，但不得因此丢句。"
)

# 文言 → 现代汉语。与英译中不同，这里不是跨语言翻译，而是同语言的历时改写：
# 关键是「不加戏、不漏句、不文白夹杂」，专名与典制保持原样。
MODERN_SYSTEM = (
    "你是古籍今译专家，负责把文言文改写为准确、通顺的现代汉语。严格遵守：\n"
    "1. 只输出一个 JSON 对象，形如 {\"paras\":[\"第一段\",\"第二段\"]}；\n"
    "2. paras 的条数必须与输入段落数完全相同，逐段一一对应，不得合并、拆分、增删、遗漏；\n"
    "3. 忠实原意，不增删、不引申、不评论；原文省略的主语可依上下文补出，但不得添加原文没有的内容；\n"
    "4. 人名、地名、官名、书名、年号保留原字；生僻的典章制度、名物首次出现可加简短括注；\n"
    "5. 使用规范现代书面语，避免文白夹杂与过度口语化，保留原文的层次、语气与修辞；\n"
    "6. 引文、对话、数字、干支纪年照录，不改成公历，不翻译诗句为散文；\n"
    "7. 不要输出任何解释、前言、注释段落或 markdown 代码块围栏。"
)

_lock = threading.Lock()
_cfg_state = {"mtime": -1.0, "cfg": {}}
_model_state = {"model": None, "at": 0.0}
_opt_state = {"ok": True}   # 可选参数（关思维链 / JSON 模式）是否被服务端接受
# 落盘健康度：写入失败不再静默，状态接口可查，便于发现只读文件系统
_write_state = {"writes": 0, "errors": 0, "last_error": "", "last_error_at": 0}


# ---------------------------------------------------------------- 配置
def _read_file_cfg() -> dict:
    best, mt = {}, -1.0
    for p in SECRETS:
        if not os.path.exists(p):
            continue
        m = os.path.getmtime(p)
        if m <= mt:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            d = {}
        if d:
            best, mt = d, m
    if mt != _cfg_state["mtime"]:
        _cfg_state["cfg"] = best
        _cfg_state["mtime"] = mt
        _model_state["model"] = None
    return _cfg_state["cfg"]


def _normalize_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        url = "https://" + url
    url = re.sub(r"/chat/completions$", "", url)
    # 只给了域名（无路径）时补 /v1
    rest = re.sub(r"^https?://[^/]+", "", url)
    if rest in ("", "/"):
        url += "/v1"
    return url


def config() -> dict:
    f = _read_file_cfg()
    env = os.environ
    base = (
        env.get("TRANSLATE_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or env.get("OPENAI_API_BASE")
        or f.get("base_url")
        or ""
    )
    key = (
        env.get("TRANSLATE_API_KEY")
        or env.get("OPENAI_API_KEY")
        or f.get("api_key")
        or ""
    )
    model = env.get("TRANSLATE_MODEL") or f.get("model") or ""
    try:
        workers = int(env.get("TRANSLATE_WORKERS") or f.get("workers") or WORKERS)
    except Exception:
        workers = WORKERS
    think = f.get("disable_thinking", True)
    json_mode = f.get("json_mode", True)
    return {
        "base_url": _normalize_base(base),
        "api_key": key.strip(),
        "model": model.strip(),
        "workers": max(1, min(6, workers)),
        "disable_thinking": bool(think),
        "json_mode": bool(json_mode),
    }


def enabled() -> bool:
    c = config()
    return bool(c["base_url"] and c["api_key"])


def status() -> dict:
    c = config()
    books = 0
    chapters = 0
    if os.path.isdir(CACHE_DIR):
        for bid in os.listdir(CACHE_DIR):
            folder = os.path.join(CACHE_DIR, bid)
            if not os.path.isdir(folder):
                continue
            n = 0
            for fn in os.listdir(folder):
                if fn.endswith(".json") and fn != "index.json":
                    n += 1
            if n:
                books += 1
                chapters += n
    target = CACHE_DIR if os.path.isdir(CACHE_DIR) else BASE
    return {
        "enabled": enabled(),
        "base_host": re.sub(r"^https?://", "", c["base_url"]).split("/")[0] if c["base_url"] else "",
        "model": resolve_model() if enabled() else "",
        "cached_books": books,
        "cached_chapters": chapters,
        "storage": os.path.relpath(CACHE_DIR, BASE),
        "writable": os.access(target, os.W_OK),
        "writes": _write_state["writes"],
        "write_errors": _write_state["errors"],
        "last_error": _write_state["last_error"],
        "last_error_at": _write_state["last_error_at"],
    }


def resolve_model() -> str:
    c = config()
    if c["model"]:
        return c["model"]
    now = time.time()
    with _lock:
        if _model_state["model"] and now - _model_state["at"] < 3600:
            return _model_state["model"]
    base, key = c["base_url"], c["api_key"]
    if not (base and key):
        return ""
    ids: list[str] = []
    try:
        r = requests.get(
            base + "/models",
            headers={"Authorization": "Bearer " + key},
            timeout=20,
        )
        if r.ok:
            data = r.json().get("data") or r.json().get("models") or []
            ids = [d.get("id") or d.get("name") for d in data if isinstance(d, dict)]
            ids = [i for i in ids if i]
    except Exception:
        ids = []

    chosen = ""
    if ids:
        bad = re.compile(
            r"embed|whisper|tts|audio|voice|image|dall|moderation|rerank|vision|minicpm-v|clef",
            re.I,
        )
        cand = [i for i in ids if not bad.search(i)]
        # 优先 MiMo-V2.6-Flash；其次其他同档 flash 模型（快、便宜、中文稳）
        prefer = [
            "mimo-v2.6-flash", "mimo-v2", "mimo",
            "qwen3.8-flash", "deepseek-v4.1-flash", "glm-5.3-flash",
            "deepseek-v4-flash", "qwen-flash", "qwen-plus",
            "gpt-4o-mini", "gpt-4.1-mini", "deepseek-chat",
            "claude-3-5-haiku", "gemini-2.0-flash",
        ]
        for p in prefer:
            hit = [i for i in cand if p in i.lower()]
            if hit:
                chosen = sorted(hit, key=len)[0]
                break
        if not chosen and cand:
            chosen = cand[0]
    with _lock:
        _model_state["model"] = chosen or "MiMo-V2.6-Flash"
        _model_state["at"] = now
    return _model_state["model"]


# ---------------------------------------------------------------- 调用
def _chat(payload: list[dict], model: str) -> tuple[str, str]:
    """返回 (正文, finish_reason)。自动关闭思维链、启用 JSON 模式，不支持时回退。"""
    c = config()
    url = c["base_url"] + "/chat/completions"
    headers = {
        "Authorization": "Bearer " + c["api_key"],
        "Content-Type": "application/json",
    }
    extra = {}
    if _opt_state["ok"]:
        if c["disable_thinking"]:
            extra["chat_template_kwargs"] = {"enable_thinking": False}
        if c["json_mode"]:
            extra["response_format"] = {"type": "json_object"}

    body = {
        "model": model,
        "messages": payload,
        "temperature": 0.25,
        "max_tokens": 6000,
    }

    r = None
    for _ in range(2):
        try:
            r = requests.post(url, headers=headers, json={**body, **extra}, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            raise RuntimeError("接口超时（180 秒无响应）")
        except requests.exceptions.RequestException:
            raise RuntimeError("接口无法连接：" + c["base_url"])
        if r.status_code in (400, 422) and extra:
            extra = {}
            _opt_state["ok"] = False
            continue
        break

    if not r.ok:
        detail = ""
        try:
            j = r.json()
            detail = (j.get("error") or {}).get("message") or json.dumps(j, ensure_ascii=False)[:300]
        except Exception:
            detail = (r.text or "")[:300]
        raise RuntimeError(f"接口返回 {r.status_code}：{detail}")

    j = r.json()
    try:
        ch = j["choices"][0]
        content = ch["message"].get("content") or ""
        finish = ch.get("finish_reason") or ""
    except Exception:
        raise RuntimeError("接口返回格式异常：" + json.dumps(j, ensure_ascii=False)[:200])

    if finish == "length":
        raise RuntimeError("输出被截断（max_tokens 不足）")
    return content, finish


def _parse_json_obj(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    t = t.replace("\u2028", " ").replace("\u2029", " ")
    return json.loads(t)


def _chunk(paras: Iterable[str]) -> list[list[int]]:
    """按字符与段数把段落索引分组。"""
    blocks, cur, size = [], [], 0
    for i, p in enumerate(paras):
        n = len(p)
        if cur and (size + n > MAX_BLOCK_CHARS or len(cur) >= MAX_BLOCK_PARAS):
            blocks.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += n
    if cur:
        blocks.append(cur)
    return blocks


def _split_long(p: str) -> list[str]:
    if len(p) <= HARD_PARA_LIMIT:
        return [p]
    out, buf = [], ""
    for sent in re.split(r"(?<=[.!?;:])\s+", p):
        if len(buf) + len(sent) > HARD_PARA_LIMIT - 200:
            out.append(buf.strip())
            buf = ""
        buf += sent + " "
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


# ---------------------------------------------------------------- 缓存
def _cache_path(bid: str, idx: int) -> str:
    return os.path.join(CACHE_DIR, bid, f"{idx}.json")


def load_cache(bid: str, idx: int) -> dict | None:
    p = _cache_path(bid, idx)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def drop_cache(bid: str, idx: int) -> None:
    """译文已经合并进书里时，删掉这份重复的缓存文件。

    index.json 保留：目录译名和「已译」标记还要读它，且它只有几百字节。
    """
    try:
        os.remove(_cache_path(bid, idx))
    except OSError:
        pass


def _index_path(bid: str) -> str:
    return os.path.join(CACHE_DIR, bid, "index.json")


def _note_error(e) -> None:
    _write_state["errors"] += 1
    _write_state["last_error"] = f"{type(e).__name__}: {e}"[:300]
    _write_state["last_error_at"] = int(time.time())
    print("[trans] 缓存写入失败:", _write_state["last_error"], flush=True)


def _update_index(bid: str, idx: int, cn_title: str, done: bool):
    """维护每本书的章节译文索引，供书架/目录一次性读取。"""
    p = _index_path(bid)
    try:
        d = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                d = json.load(f) or {}
        rec = d.get(str(idx)) or {}
        if cn_title:
            rec["t"] = cn_title
        rec["done"] = bool(done)
        d[str(idx)] = rec
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception as e:  # noqa: BLE001
        _note_error(e)


def titles(bid: str) -> dict[int, str]:
    p = _index_path(bid)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f) or {}
            return {int(k): (v or {}).get("t", "") for k, v in d.items()}
        except Exception:
            return {}
    # 索引缺失时按章文件回填（兼容先上线、后建索引的缓存）
    folder = os.path.join(CACHE_DIR, bid)
    if not os.path.isdir(folder):
        return {}
    out: dict[int, str] = {}
    for fn in os.listdir(folder):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        try:
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                rec = json.load(f) or {}
            out[int(fn[:-5])] = rec.get("cn_title") or ""
        except Exception:
            continue
    return out


def save_cache(bid: str, idx: int, cn: list[str], cn_title: str, model: str, done: bool) -> bool:
    ok = True
    try:
        os.makedirs(os.path.join(CACHE_DIR, bid), exist_ok=True)
        tmp = _cache_path(bid, idx) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"cn": cn, "cn_title": cn_title, "model": model,
                 "done": done, "at": int(time.time())},
                f, ensure_ascii=False,
            )
        os.replace(tmp, _cache_path(bid, idx))
        _write_state["writes"] += 1
    except Exception as e:  # noqa: BLE001
        ok = False
        _note_error(e)
    _update_index(bid, idx, cn_title, done)
    return ok


def book_has_cn(bid: str) -> bool:
    d = os.path.join(CACHE_DIR, bid)
    if not os.path.isdir(d):
        return False
    return any(x.endswith(".json") and x != "index.json" for x in os.listdir(d))


# ---------------------------------------------------------------- 导出 / 清单
def export_book(bid: str) -> dict | None:
    """把一本书的全部译文打成可搬运的结构（供离线备份、迁移到发布包）。"""
    folder = os.path.join(CACHE_DIR, bid)
    if not os.path.isdir(folder):
        return None
    chapters = {}
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        try:
            idx = int(fn[:-5])
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                d = json.load(f) or {}
        except Exception:
            continue
        cn = d.get("cn") or []
        if not any(str(x).strip() for x in cn):
            continue
        chapters[str(idx)] = {
            "cn": cn,
            "t": d.get("cn_title") or "",
            "done": bool(d.get("done")),
            "at": int(d.get("at") or 0),
            "model": d.get("model") or "",
        }
    if not chapters:
        return None
    return {"id": bid, "v": 1, "chapters": chapters}


def export_all(ids: Iterable[str] | None = None) -> dict:
    books = {}
    if ids is None:
        ids = [d for d in os.listdir(CACHE_DIR)] if os.path.isdir(CACHE_DIR) else []
    for bid in ids:
        rec = export_book(bid)
        if rec:
            books[bid] = rec
    return {"v": 1, "at": int(time.time()), "books": books}


def manifest() -> dict[str, dict]:
    """轻量清单：{书号: {n: 已译章数, done: 全章译完的章数, t: 书名?}}，只读 index。"""
    out: dict[str, dict] = {}
    if not os.path.isdir(CACHE_DIR):
        return out
    for bid in os.listdir(CACHE_DIR):
        folder = os.path.join(CACHE_DIR, bid)
        if not os.path.isdir(folder):
            continue
        idxp = _index_path(bid)
        n = done_n = 0
        if os.path.exists(idxp):
            try:
                with open(idxp, encoding="utf-8") as f:
                    d = json.load(f) or {}
                n = len([k for k, v in d.items() if (v or {}).get("t") or (v or {}).get("done")])
                done_n = len([k for k, v in d.items() if (v or {}).get("done")])
            except Exception:
                n = done_n = 0
        if not n:
            n = len([x for x in os.listdir(folder) if x.endswith(".json") and x != "index.json"])
            done_n = n
        if n:
            out[bid] = {"n": n, "done": done_n}
    return out


# ---------------------------------------------------------------- 主流程
def translate_chapter(book: dict, idx: int) -> Generator[dict, None, None]:
    """逐块产出事件：meta / prog / part / done / err。"""
    if not enabled():
        yield {"t": "err", "msg": "尚未配置翻译接口"}
        return

    ch = book["chapters"][idx]
    paras = ch["text"].split("\n")
    real = [i for i, p in enumerate(paras) if p.strip()]

    cache = load_cache(book["id"], idx)
    cn = list(cache["cn"]) if cache and len(cache.get("cn") or []) == len(paras) else [""] * len(paras)
    cn_title = (cache or {}).get("cn_title") or ""
    if cache and cache.get("done"):
        yield {"t": "done", "cn": cn, "cnTitle": cn_title, "cached": True}
        return

    todo = [i for i in real if not cn[i].strip()]
    blocks = _chunk([paras[i] for i in todo]) if todo else []
    model = resolve_model()

    yield {"t": "meta", "blocks": len(blocks), "model": model, "total": len(paras)}

    if not blocks:
        save_cache(book["id"], idx, cn, cn_title, model, True)
        yield {"t": "done", "cn": cn, "cnTitle": cn_title, "cached": True}
        return

    is_modern = book.get("lang", "zh") == "zh"
    sys_prompt = MODERN_SYSTEM if is_modern else SYSTEM
    if is_modern:
        ctx = (f"书名：{book['title']}；作者：{book.get('author','')}。"
               "以下为文言原文，请逐段今译为现代汉语。")
    else:
        ctx = f"书名：{book['title']}；作者：{book.get('author','')}。"

    jobs = []
    for bi, block in enumerate(blocks):
        part_ids = [todo[k] for k in block]
        jobs.append((bi, part_ids, [paras[i] for i in part_ids]))

    def _work(job):
        bi, part_ids, src = job
        # 超长段落拆分后请求，再合并回原段落
        pieces: list[str] = []
        owner: list[int] = []
        for j, s in enumerate(src):
            for piece in _split_long(s):
                pieces.append(piece)
                owner.append(j)

        # 中文古籍的章节标题本就是中文，无需模型改写
        want_title = bi == 0 and not cn_title and not is_modern
        user = json.dumps(
            {"title": ch["title"] if want_title else "", "paras": pieces},
            ensure_ascii=False,
        )
        ask = "请翻译以下 JSON 中的内容：" if not is_modern else "请今译以下 JSON 中的段落："
        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": ctx + "\n" + ask + "\n" + user},
        ]

        last_err = ""
        for attempt in range(4):
            try:
                raw, _ = _chat(msgs, model)
                obj = _parse_json_obj(raw)
                arr = obj.get("paras") or obj.get("paragraphs") or obj.get("cn") or []
                arr = [str(x).strip() for x in arr]
                if len(arr) == len(pieces):
                    return bi, part_ids, owner, arr, str(obj.get("title") or "").strip()
                last_err = f"段落数不符（期望 {len(pieces)}，实际 {len(arr)}）"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:200]
            time.sleep(6 if "429" in last_err else 1.2 * (attempt + 1))
        raise RuntimeError(f"第 {bi + 1}/{len(blocks)} 块翻译失败：{last_err}")

    total = len(jobs)
    finished = 0
    ex = ThreadPoolExecutor(max_workers=min(config()["workers"], total))
    try:
        futs = [ex.submit(_work, j) for j in jobs]
        for fut in as_completed(futs):
            try:
                bi, part_ids, owner, arr, title_cn = fut.result()
            except Exception as e:  # noqa: BLE001
                for f in futs:
                    f.cancel()
                save_cache(book["id"], idx, cn, cn_title, model, False)
                yield {"t": "err", "msg": str(e)[:220]}
                return

            if title_cn and not cn_title:
                cn_title = title_cn
            merged: dict[int, list[str]] = {}
            for j, txt in zip(owner, arr):
                merged.setdefault(j, []).append(txt)
            for j, txts in merged.items():
                cn[part_ids[j]] = " ".join(x for x in txts if x).strip()

            finished += 1
            save_cache(book["id"], idx, cn, cn_title, model, finished == total)
            yield {
                "t": "part", "done": finished, "total": total,
                "cn": cn, "cnTitle": cn_title,
            }
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    yield {"t": "done", "cn": cn, "cnTitle": cn_title, "cached": False}


def translate_book(book: dict) -> Generator[tuple[int, dict], None, None]:
    for i in range(len(book["chapters"])):
        for ev in translate_chapter(book, i):
            yield i, ev


if __name__ == "__main__":
    import argparse
    import gzip

    ap = argparse.ArgumentParser(description="实时/批量翻译英文书")
    ap.add_argument("--book", default=None)
    ap.add_argument("--ch", type=int, default=None)
    ap.add_argument("--check", action="store_true", help="只检查配置与模型")
    ap.add_argument("--books-dir", default=os.path.join(BASE, "data", "books"))
    args = ap.parse_args()

    if args.check or not args.book:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        raise SystemExit(0)

    with gzip.open(os.path.join(args.books_dir, args.book + ".json.gz"), "rt", encoding="utf-8") as f:
        bk = json.load(f)

    if not enabled():
        raise SystemExit("未配置接口：请设置 TRANSLATE_BASE_URL / TRANSLATE_API_KEY，或写入 .secrets/translate.json")

    print("model:", resolve_model())
    rng = [args.ch] if args.ch is not None else range(len(bk["chapters"]))
    for i in rng:
        print(f"--- ch{i} {bk['chapters'][i]['title'][:40]} ---")
        for ev in translate_chapter(bk, i):
            print(" ", ev.get("t"), ev.get("msg", ""), ev.get("done", ""), ev.get("total", ""))
