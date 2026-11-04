"""批量翻译英文书的章节标题（目录用），不触碰正文。

产物：data/cn_titles.json
    {"en1232": {"t": ["第一章 · 君主国有多少种类", ...], "done": true}}

- 仅翻译「含拉丁字母且无中文」的标题；其余原样保留。
- 分批（默认 30 条/次）请求，逐批落盘，可中断续跑。
- 已有中文的标题不会重复翻译。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trans  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(DATA, "cn_titles.json")
CJK = re.compile(r"[\u4e00-\u9fa5]")

SYSTEM = (
    "你是专业译者，负责把英文书籍的章节标题译成简体中文。严格遵循：\n"
    "1. 只输出 JSON 对象 {\"titles\":[\"译名1\",\"译名2\"]}，条数与输入完全一致；\n"
    "2. 保留编号层级并译为中文：Chapter I→第一章，Book II→第二卷，Part III→第三部，"
    "Canto IV→第四篇，Act V→第五幕，Scene 2→第二场，Letter 6→第六封信，Psalm 23→第二十三篇；\n"
    "3. 原标题用「·」分隔的层级照旧保留（如“第一章 · 论世袭君主国”）；\n"
    "4. 全大写标题按正常大小写理解后意译，不要保留全大写；\n"
    "5. 人名、地名、书名用汉语通行译名；不要添加译注或解释，不加句号；\n"
    "6. 无法判断含义的专名（如拉丁篇名）音译，不要留英文。"
)

_lock = threading.Lock()
_state: dict[str, dict] = {}
_model = ""


def load():
    global _state
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                _state = json.load(f) or {}
        except Exception:
            _state = {}
    return _state


def save():
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_state, f, ensure_ascii=False)
    os.replace(tmp, OUT)


def need_translate(t: str) -> bool:
    return bool(t) and not CJK.search(t) and bool(re.search(r"[A-Za-z]", t))


def translate_batch(titles: list[str]) -> list[str] | None:
    payload = json.dumps({"titles": titles}, ensure_ascii=False)
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "请翻译下列章节标题：" + payload},
    ]
    last = ""
    for attempt in range(4):
        try:
            raw, _ = trans._chat(msgs, _model)
            obj = trans._parse_json_obj(raw)
            arr = obj.get("titles") or obj.get("paras") or []
            arr = [str(x).strip() for x in arr]
            if len(arr) == len(titles):
                return arr
            last = f"数量不符 {len(arr)} != {len(titles)}"
        except Exception as e:  # noqa: BLE001
            last = str(e)[:160]
        time.sleep(8 if "429" in last else 2 * (attempt + 1))
    print("  ! 批次失败:", last, "|", titles[0][:40], file=sys.stderr)
    return None


def main():
    global _model
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--book", default=None, help="只处理某本书")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not trans.enabled():
        raise SystemExit("未配置翻译接口")

    _model = trans.resolve_model()
    print("model:", _model)

    lib = json.load(open(os.path.join(DATA, "library.json"), encoding="utf-8"))
    books = [b for b in lib if b.get("lang") == "en" and (not args.book or b["id"] == args.book)]
    load()

    tasks = []
    for b in books:
        with gzip.open(os.path.join(DATA, "books", b["id"] + ".json.gz"), "rt", encoding="utf-8") as f:
            d = json.load(f)
        titles = [c["title"] for c in d["chapters"]]
        rec = _state.get(b["id"]) or {}
        cur = rec.get("t") or []
        if len(cur) != len(titles):
            cur = list(titles)          # 未译位置先放原文占位
        _state[b["id"]] = {"t": cur}
        pos = [i for i, t in enumerate(cur) if need_translate(t)]
        for k in range(0, len(pos), args.batch):
            chunk = pos[k:k + args.batch]
            tasks.append((b["id"], chunk, [cur[i] for i in chunk]))

    print("书 %d 本 | 待译标题 %d | 批次 %d" % (len(books), sum(len(t[1]) for t in tasks), len(tasks)))
    if args.dry_run:
        return
    if not tasks:
        print("全部已有中文标题")
        return

    done_titles = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(translate_batch, t[2]): t for t in tasks}
        for n, fut in enumerate(as_completed(futs), 1):
            bid, chunk, src = futs[fut]
            arr = fut.result()
            if arr:
                with _lock:
                    row = _state[bid]["t"]
                    for i, v in zip(chunk, arr):
                        if v:
                            row[i] = v
                    done_titles += len(chunk)
                    _state[bid]["done"] = not any(need_translate(x) for x in row)
                    save()
            el = time.time() - t0
            print("[%d/%d] %s +%d  已译 %d  用时 %.0fs" %
                  (n, len(tasks), bid, len(chunk) if arr else 0, done_titles, el), flush=True)

    load()
    left = sum(1 for r in _state.values() for x in r.get("t", []) if need_translate(x))
    print("完成。剩余未译标题：", left)


if __name__ == "__main__":
    main()
