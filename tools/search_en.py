#!/usr/bin/env python3
"""在西文 Gutenberg 里按关键词搜书，输出候选（供人工挑选 id）"""
import html
import re
import time
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

QUERIES = [
    "notebooks leonardo da vinci", "euclid elements geometry", "newton principia",
    "origin of species darwin", "voyage of the beagle", "relativity einstein",
    "galileo two new sciences", "chemical history of a candle", "descent of man darwin",
    "novum organum bacon", "decline and fall roman empire", "herodotus histories",
    "thucydides peloponnesian war", "plutarch lives", "caesar gallic war",
    "meditations marcus aurelius", "republic plato", "nicomachean ethics aristotle",
    "prince machiavelli", "wealth of nations smith", "utopia thomas more",
    "discourse on method descartes", "critique of pure reason kant",
    "thus spoke zarathustra", "on liberty mill", "social contract rousseau",
    "leviathan hobbes", "confessions augustine", "summa theologica aquinas",
    "odyssey homer", "iliad homer", "divine comedy dante", "don quixote cervantes",
    "war and peace tolstoy", "crime and punishment dostoevsky", "les miserables hugo",
    "tale of two cities dickens", "pride and prejudice austen", "moby dick melville",
    "huckleberry finn twain", "frankenstein shelley", "dracula stoker",
    "twenty thousand leagues verne", "time machine wells", "sherlock holmes doyle",
    "faust goethe", "paradise lost milton", "essays montaigne",
    "history of the peloponnesian war", "anabasis xenophon", "annals tacitus",
    "antiquities of the jews", "history of rome mommsen", "french revolution carlyle",
    "art of war sun tzu", "analects confucius", "meditations descartes",
    "wealth of nations", "on the origin of species", "principia mathematica newton",
    "history of animals aristotle", "natural history pliny", "on the soul aristotle",
    "experimental researches electricity faraday", "principle of population malthus",
    "astronomia nova kepler", "on the revolutions copernicus",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "ignore")


def search(q):
    url = "https://www.gutenberg.org/ebooks/search/?query=" + urllib.parse.quote(q)
    s = fetch(url)
    out = []
    for it in re.findall(r'<li class="booklink">(.*?)</li>', s, re.S):
        a = re.search(r'href="/ebooks/(\d+)"', it)
        t = re.search(r'class="title">(.*?)</span>', it, re.S)
        sub = re.search(r'class="subtitle">(.*?)</span>', it, re.S)
        if not a:
            continue
        out.append((a.group(1),
                    html.unescape(re.sub("<[^>]+>", "", t.group(1))).strip() if t else "",
                    html.unescape(re.sub("<[^>]+>", "", sub.group(1))).strip() if sub else ""))
    return out[:3]


if __name__ == "__main__":
    for q in QUERIES:
        try:
            rs = search(q)
        except Exception as e:
            print(f"## {q} -> ERR {e}")
            continue
        print(f"## {q}")
        for bid, t, sub in rs:
            print(f"   {bid:>6} | {t[:66]} | {sub[:34]}")
        time.sleep(0.35)
