"""用修正后的解析器重取章节标题，只替换 title，不动正文与已有译文。

章节数不一致的书会被跳过并列出，不做猜测性对齐。
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import en_parse  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def save_book(bid: str, book: dict):
    path = os.path.join(DATA, "books", bid + ".json.gz")
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--book", default=None)
    ap.add_argument("--changes-out", default=None, help="把变更写入 JSON，供重译使用")
    args = ap.parse_args()

    changes = []

    lib = json.load(open(os.path.join(DATA, "library.json"), encoding="utf-8"))
    books = [b for b in lib if b.get("lang") == "en" and (not args.book or b["id"] == args.book)]
    ok = bad = changed = 0
    mismatched = []

    for b in books:
        bid = b["id"]
        raw = os.path.join(args.raw_dir, bid.replace("en", "", 1) + ".txt")
        if not os.path.exists(raw):
            continue
        text = open(raw, encoding="utf-8", errors="ignore").read()
        new, kind, words = en_parse.parse(text)
        with gzip.open(os.path.join(DATA, "books", bid + ".json.gz"), "rt", encoding="utf-8") as f:
            book = json.load(f)
        if len(new) != len(book["chapters"]):
            mismatched.append((bid, b["title"], len(book["chapters"]), len(new)))
            bad += 1
            continue
        diffs = 0
        for idx, (old_c, new_c) in enumerate(zip(book["chapters"], new)):
            if new_c["title"] != old_c["title"]:
                changes.append({"id": bid, "i": idx, "old": old_c["title"], "new": new_c["title"]})
                old_c["title"] = new_c["title"]
                diffs += 1
        if diffs:
            changed += 1
            if args.apply:
                save_book(bid, book)
        ok += 1
        print("%-8s %-16s 标题更新 %d/%d" % (bid, b["title"][:14], diffs, len(new)), flush=True)

    print("\n一致 %d 本（其中 %d 本有标题更新）| 章节数不一致 %d 本" % (ok, changed, bad))
    for m in mismatched:
        print("  跳过", m)
    if args.changes_out:
        with open(args.changes_out, "w", encoding="utf-8") as f:
            json.dump(changes, f, ensure_ascii=False, indent=1)
        print("变更 %d 条 → %s" % (len(changes), args.changes_out))


if __name__ == "__main__":
    main()
