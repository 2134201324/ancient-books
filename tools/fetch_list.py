#!/usr/bin/env python3
"""抓 Gutenberg 中文藏书全量清单"""
import json, re, html, time, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
BASE = "https://www.gutenberg.org/ebooks/search/?query=l.zh&sort_order=downloads&start_index={}"

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")

books = {}
start = 1
while start < 400:
    try:
        s = fetch(BASE.format(start))
    except Exception as e:
        print("fail", start, e); break
    items = re.findall(r'<li class="booklink">(.*?)</li>', s, re.S)
    if not items:
        print("empty at", start); break
    new = 0
    for it in items:
        aid = re.search(r'href="(/ebooks/(\d+))"', it)
        if not aid: continue
        bid = aid.group(2)
        t = re.search(r'class="title">(.*?)</span>', it, re.S)
        sub = re.search(r'class="subtitle">(.*?)</span>', it, re.S)
        dl = re.search(r'class="extra">(.*?)</span>', it, re.S)
        title = html.unescape(re.sub("<[^>]+>", "", t.group(1))).strip() if t else ""
        author = html.unescape(re.sub("<[^>]+>", "", sub.group(1))).strip() if sub else ""
        if bid not in books:
            books[bid] = {"id": bid, "title": title, "author": author,
                          "downloads": int(re.sub(r"\D", "", dl.group(1)) or 0) if dl else 0}
            new += 1
    print(f"start={start} got={len(items)} new={new} total={len(books)}")
    if new == 0: break
    start += 25
    time.sleep(0.4)

json.dump(list(books.values()), open("/root/.codebuddy/artifact/2f8a7d30-9c21-4f0b-1d60-0e353836f000/data/raw_list.json", "w"), ensure_ascii=False, indent=1)
print("TOTAL", len(books))
