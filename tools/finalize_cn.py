#!/usr/bin/env python3.11
"""把翻译产物（data/books/<id>.cn.json 或若干 cnN.json 分段）合并进书籍文件。

用法
----
  python3.11 tools/finalize_cn.py --book en59 \
      --parts-dir /path/to/work --books-dir data/books --lib data/library.json
"""
import argparse
import glob
import gzip
import json
import os


def load_book(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def save_book(path, book):
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--parts-dir", required=True, help="含 cn.json 或 cn0.json..cnN.json 的目录")
    ap.add_argument("--books-dir", default="data/books")
    ap.add_argument("--lib", default="data/library.json")
    args = ap.parse_args()

    bpath = os.path.join(args.books_dir, f"{args.book}.json.gz")
    book = load_book(bpath)
    chapters = book["chapters"]

    results = {}
    single = os.path.join(args.parts_dir, "cn.json")
    if os.path.exists(single):
        files = [single]
    else:
        files = sorted(glob.glob(os.path.join(args.parts_dir, "cn*.json")))
    # 同一章可分多个文件（如 cn5a.json / cn5b.json），按 i 拼接 cn 列表
    for p in files:
        for d in json.load(open(p, encoding="utf-8")):
            i = d["i"]
            if i not in results:
                results[i] = {"i": i, "cn_title": d.get("cn_title", ""), "cn": list(d.get("cn", []))}
            else:
                if d.get("cn_title"):
                    results[i]["cn_title"] = d["cn_title"]
                results[i]["cn"].extend(d.get("cn", []))

    ok = 0
    for i, ch in enumerate(chapters):
        if i in results and results[i].get("cn"):
            ch["cn_title"] = results[i].get("cn_title", "")
            ch["cn"] = results[i]["cn"]
            ok += 1
    book["has_cn"] = ok > 0
    save_book(bpath, book)

    if os.path.exists(args.lib):
        lib = json.load(open(args.lib, encoding="utf-8"))
        for b in lib:
            if b["id"] == args.book:
                b["has_cn"] = book["has_cn"]
        json.dump(lib, open(args.lib, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    print(f"已合并 {ok}/{len(chapters)} 章中文译本，has_cn={book['has_cn']}")


if __name__ == "__main__":
    main()
