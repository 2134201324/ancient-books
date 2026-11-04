"""把 data/cn_cache 里已完成的译文合并进书籍数据（data/books/*.json.gz）。

为什么需要：云端容器的运行期写入不保证跨重建保留，发布包才是可靠载体。
合并后译文随 data/books 一起发布，任何实例、任何重启都能直接读到。

只合并 done=True 且段落数与原文严格一致的章节，避免半成品污染正文。

用法：
    python3.11 tools/merge_cn.py [--dry-run] [--book en1232]
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_book(path: str) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _save_book(path: str, book: dict) -> None:
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False)
    os.replace(tmp, path)


def merge_all(books_dir: str, cache_dir: str, only: str | None = None, dry: bool = False) -> dict:
    lib_path = os.path.join(os.path.dirname(books_dir), "library.json")
    lib = []
    if os.path.exists(lib_path):
        with open(lib_path, encoding="utf-8") as f:
            lib = json.load(f) or []
    lib_changed = False
    stats = {"books": 0, "chapters": 0, "skipped": 0}

    for folder in sorted(glob.glob(os.path.join(cache_dir, "*"))):
        if not os.path.isdir(folder):
            continue
        bid = os.path.basename(folder)
        if only and bid != only:
            continue
        path = os.path.join(books_dir, f"{bid}.json.gz")
        if not os.path.exists(path):
            continue
        book = _load_book(path)
        if book.get("lang") != "en":
            continue
        chs = book.get("chapters") or []
        got = 0
        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".json") or fn == "index.json":
                continue
            try:
                idx = int(fn[:-5])
                with open(os.path.join(folder, fn), encoding="utf-8") as f:
                    rec = json.load(f) or {}
            except Exception:
                continue
            if idx < 0 or idx >= len(chs):
                stats["skipped"] += 1
                continue
            if not rec.get("done"):
                stats["skipped"] += 1
                continue
            cn = rec.get("cn") or []
            want = len(chs[idx]["text"].split("\n"))
            if len(cn) != want or not any(str(x).strip() for x in cn):
                stats["skipped"] += 1
                continue
            if chs[idx].get("cn") != cn:
                chs[idx]["cn"] = cn
                got += 1
            if rec.get("cn_title"):
                chs[idx]["cn_title"] = rec["cn_title"]
        if not got and not book.get("has_cn"):
            continue
        if got:
            book["has_cn"] = True
            stats["books"] += 1
            stats["chapters"] += got
            print(f"  {bid}: 合并 {got} 章 -> {book.get('title','')[:30]}")
            if not dry:
                _save_book(path, book)
        else:
            print(f"  {bid}: 书籍已内嵌译文，仅同步书库标志")
        for b in lib:
            if b.get("id") == bid and not b.get("has_cn"):
                b["has_cn"] = True
                lib_changed = True
    if lib_changed and not dry:
        tmp = lib_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False)
        os.replace(tmp, lib_path)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--books-dir", default=os.path.join(BASE, "data", "books"))
    ap.add_argument("--cache-dir", default=os.path.join(BASE, "data", "cn_cache"))
    ap.add_argument("--book", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = merge_all(args.books_dir, args.cache_dir, args.book, args.dry_run)
    print(f"完成：{stats['books']} 本 / {stats['chapters']} 章合并，跳过 {stats['skipped']} 章")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
