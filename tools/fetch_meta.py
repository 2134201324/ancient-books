#!/usr/bin/env python3
"""抓每本书的 Gutenberg metadata（subject / 分类）"""
import json, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
DATA = os.path.dirname(os.path.abspath(__file__))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "ignore")


def one(bid):
    try:
        s = fetch(f"https://www.gutenberg.org/ebooks/{bid}")
    except Exception as e:
        return bid, None
    subs = re.findall(r"<th>\s*(?:Subject|Category)\s*</th>\s*<td[^>]*>(.*?)</td>", s, re.S)
    if not subs:
        subs = re.findall(r'property="dcterms:subject"[^>]*>(.*?)</td>', s, re.S)
    out = []
    for x in subs:
        t = re.sub(r"<[^>]+>", "", x).strip()
        if t and t not in out:
            out.append(t)
    return bid, out


def main():
    ids = sys.argv[1:]
    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(one, i) for i in ids]
        for f in as_completed(futs):
            bid, sub = f.result()
            res[bid] = sub or []
    json.dump(res, open(os.path.join(DATA, "meta.json"), "w"), ensure_ascii=False, indent=1)
    print("done", len(res))


if __name__ == "__main__":
    main()
