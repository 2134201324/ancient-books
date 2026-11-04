#!/usr/bin/env python3
"""最终构建：重新分章 -> 分类过滤 -> 去重 -> 输出站点数据"""
import gzip, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import strip_pg, CC
from parser2 import parse, cjk_count

SRC = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SRC, "raw")
DST = "/workspace/gutenberg-reader/data"
BOOKS = os.path.join(DST, "books")
os.makedirs(BOOKS, exist_ok=True)

META = json.load(open(os.path.join(SRC, "meta.json"), encoding="utf-8"))
RAW_LIST = {x["id"]: x for x in json.load(open(os.path.join(SRC, "raw_list.json"), encoding="utf-8"))}

KEY = re.compile(r"fiction|short stories|legends|ghost stories|folklore|fantasy|drama|novel|tales", re.I)
STOP_TITLE = re.compile(r"^第\s*[一二三四五六七八九十百千零〇两0-9]{1,8}\s*回")
DIGIT = {"〇":0,"零":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
UNIT = {"十":10,"百":100,"千":1000}

def chapter_no(title):
    m = re.match(r"^第\s*([一二三四五六七八九十百千零〇两0-9]{1,8})\s*回", title)
    if not m: return None
    s = m.group(1)
    if s.isdigit(): return int(s)
    if all(c in DIGIT for c in s):
        v = "".join(str(DIGIT[c]) for c in s)
        return int(v) if v else None
    total, cur = 0, 0
    for c in s:
        if c in DIGIT: cur = DIGIT[c]
        elif c in UNIT:
            if cur == 0: cur = 1
            total += cur * UNIT[c]; cur = 0
        else: return None
    return total + cur


def work(bid):
    path = os.path.join(RAW, f"{bid}.txt")
    if not os.path.exists(path):
        return None
    txt = open(path, encoding="utf-8", errors="ignore").read()
    body = CC.convert(strip_pg(txt))
    lines = body.split("\n")
    chapters, kind = parse(lines)
    chars = sum(sum(cjk_count(p) for p in c["paras"]) for c in chapters)
    return bid, chapters, kind, chars


def main():
    lib_raw = json.load(open(os.path.join(SRC, "library.json"), encoding="utf-8"))
    cand = [x["id"] for x in lib_raw]
    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(work, b) for b in cand]
        for f in as_completed(futs):
            r = f.result()
            if r:
                res[r[0]] = r

    records = {}
    for bid, chapters, kind, chars in res.values():
        if chars < 8000:
            continue
        subs = META.get(bid, [])
        is_fiction = any(KEY.search(s) for s in subs)
        structured = kind in ("回", "章", "卷", "篇") and len(chapters) >= 3
        if not is_fiction and not (structured and all(s == "Text" for s in subs)):
            continue
        b = RAW_LIST[bid]
        title = re.sub(r"\s*\(Chinese\)\s*$", "", b["title"]).strip()
        # 完整性：回目连续性
        nums = [chapter_no(c["title"]) for c in chapters]
        nums = [n for n in nums if n]
        missing, last = 0, 0
        if len(nums) > 2:
            nums = sorted(set(nums))
            last = nums[-1]
            missing = (last - nums[0] + 1) - len(nums)
        complete = (missing <= max(2, last * 0.03)) if last else True
        rec = {
            "id": bid, "title": title, "author": b["author"],
            "chars": chars, "n": len(chapters), "kind": kind,
            "complete": complete, "missing": missing,
            "subject": [s for s in subs if s != "Text"][:3],
            "chapters": [{"title": c["title"], "text": "\n".join(c["paras"])} for c in chapters],
        }
        # 同名去重：保留字数多的
        old = records.get(title)
        if not old or rec["chars"] > old["chars"]:
            records[title] = rec

    # 合并被 Gutenberg 拆分的分卷本（粉妝樓1-10回 / 搜神記 volume 4-10）
    SPLIT = re.compile(r"^(.+?)\s*(?:volume\s*)?(\d+)\s*[-–—]\s*(\d+)\s*(回|卷|章)?$", re.I)
    groups = {}
    for t, rec in list(records.items()):
        m = SPLIT.match(t)
        if m:
            base = m.group(1).strip()
            groups.setdefault(base, []).append((int(m.group(2)), rec, t))
    for base, arr in groups.items():
        if len(arr) < 2:
            continue
        arr.sort(key=lambda x: x[0])
        merged, seen = [], set()
        for _, rec, t in arr:
            for ch in rec["chapters"]:
                key = ch["title"]
                if key in seen:
                    continue
                seen.add(key); merged.append(ch)
            records.pop(t, None)
        head = min(arr, key=lambda x: x[0])[1]
        records[base] = {
            "id": head["id"], "title": base, "author": head["author"],
            "chars": sum(rec["chars"] for _, rec, _ in arr), "n": len(merged),
            "kind": head["kind"], "complete": head["complete"], "missing": 0,
            "subject": head["subject"], "chapters": merged,
        }

    # 近名去重：标题互相包含时保留章节更多的
    names = sorted(records.keys(), key=lambda t: len(t))
    for short in names:
        for long in list(records.keys()):
            if long == short or short not in records or long not in records:
                continue
            if short in long and records[long]["n"] >= records[short]["n"]:
                records.pop(short, None)
                break

    library = []
    for rec in records.values():
        with gzip.open(os.path.join(BOOKS, f"{rec['id']}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        library.append({
            "id": rec["id"], "title": rec["title"], "author": rec["author"],
            "chars": rec["chars"], "n": rec["n"], "kind": rec["kind"],
            "complete": rec["complete"], "subject": rec["subject"],
        })

    library.sort(key=lambda x: -x["chars"])
    json.dump(library, open(os.path.join(DST, "library.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    total = sum(os.path.getsize(os.path.join(BOOKS, f)) for f in os.listdir(BOOKS))
    print(f"books={len(library)} chars={sum(x['chars'] for x in library)} disk={total/1024/1024:.1f}MB")
    from collections import Counter
    print(Counter(x["kind"] for x in library))


if __name__ == "__main__":
    main()
