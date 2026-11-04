"""把线上已翻译的内容拉回本地工作区，写进 data/cn_cache。

用途：云端容器可能重建，运行期写入的译文会随之丢失；发布包才是唯一可靠载体。
拉回后配合 merge_cn.py 合并进书籍数据，下次发布即携带全部译文。

用法：
    python3.11 tools/sync_cn.py --url https://xxx.app.workbuddy.host --sharecode XXXX
    python3.11 tools/sync_cn.py --url ... --sharecode ... --merge
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)


def _local(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="站点地址，如 https://xxx.app.workbuddy.host")
    ap.add_argument("--sharecode", default="")
    ap.add_argument("--books-dir", default=os.path.join(BASE, "data", "books"))
    ap.add_argument("--cache-dir", default=os.path.join(BASE, "data", "cn_cache"))
    ap.add_argument("--merge", action="store_true", help="拉取后合并进书籍数据")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    url = args.url.rstrip("/") + "/api/cn/export"
    params = {"sharecode": args.sharecode} if args.sharecode else {}
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    payload = r.json()
    books = payload.get("books") or {}
    if not books:
        print("线上没有已翻译内容")
        return 0

    added = updated = skipped = 0
    for bid, rec in books.items():
        folder = os.path.join(args.cache_dir, bid)
        os.makedirs(folder, exist_ok=True)
        index_path = os.path.join(folder, "index.json")
        index = _local(index_path) or {}
        for idx_s, ch in (rec.get("chapters") or {}).items():
            p = os.path.join(folder, f"{idx_s}.json")
            old = _local(p)
            if old and int(old.get("at") or 0) >= int(ch.get("at") or 0):
                skipped += 1
                continue
            data = {
                "cn": ch.get("cn") or [],
                "cn_title": ch.get("t") or "",
                "model": ch.get("model") or "",
                "done": bool(ch.get("done")),
                "at": int(ch.get("at") or 0),
            }
            if args.dry_run:
                print(f"  [dry] {bid}/{idx_s} {len(data['cn'])} 段 done={data['done']}")
            else:
                tmp = p + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, p)
                index[idx_s] = {"t": data["cn_title"], "done": data["done"]}
            if old:
                updated += 1
            else:
                added += 1
        if not args.dry_run and index:
            tmp = index_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False)
            os.replace(tmp, index_path)

    print(f"拉取完成：新增 {added} 章，更新 {updated} 章，跳过 {skipped} 章（本地更新）")

    if args.merge and not args.dry_run:
        import merge_cn

        merge_cn.merge_all(args.books_dir, args.cache_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
