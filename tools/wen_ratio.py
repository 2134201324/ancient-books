"""给中文书打「文言程度」标记，写入 library.json 的 wen 字段。

wen = 文言虚词频率 / 白话词频率（每千字）。经验值：
    < 1     白话小说（红楼、水浒、儒林外史）
    1 ~ 2   半文半白（封神演义、镜花缘）
    >= 2    文言（史记、聊斋、论语、东周列国志）
只有 wen >= 2 的书在前端提供「白话」今译入口，避免把白话小说强行改写。
"""
from __future__ import annotations

import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import gzip

WEN = re.compile(r"[之乎者也矣焉哉曰其而乃遂亦皆莫非未]")
BAI = re.compile(r"(的|了|着|们|这|那|是|他|你|我|就|都|很|把|被|给|没|个)")
THRESHOLD = 2.0


def ratio(text: str) -> float:
    n = len(text)
    if n < 500:
        return 0.0
    w = len(WEN.findall(text)) / n * 1000
    b = len(BAI.findall(text)) / n * 1000
    return round(w / max(b, 0.01), 2)


def main() -> int:
    dry = "--apply" not in sys.argv
    path = os.path.join(BASE, "data", "library.json")
    with open(path, encoding="utf-8") as f:
        lib = json.load(f)

    changed = 0
    stats = {"modern": 0, "classical": 0}
    for b in lib:
        if b.get("lang", "zh") != "zh":
            continue
        p = os.path.join(BASE, "data", "books", f"{b['id']}.json.gz")
        if not os.path.exists(p):
            continue
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        txt = "".join(c["text"] for c in d["chapters"][:8])[:150000]
        r = ratio(txt)
        if b.get("wen") != r:
            b["wen"] = r
            changed += 1
        if r >= THRESHOLD:
            stats["classical"] += 1
        else:
            stats["modern"] += 1

    if not dry:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False)
        os.replace(tmp, path)

    print(f"{'预览' if dry else '已写入'}：更新 {changed} 本；"
          f"可今译（wen>={THRESHOLD}）{stats['classical']} 本，白话 {stats['modern']} 本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
