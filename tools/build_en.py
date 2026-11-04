#!/usr/bin/env python3
"""构建西方典籍：下载 -> 解析 -> 输出 en_books.json"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from en_parse import parse

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
SRC = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SRC, "raw_en")
os.makedirs(RAW, exist_ok=True)

# id, 中文书名, 中文作者, 分类
BOOKS = [
    # ---- 科学 ----
    ("5000", "达·芬奇笔记", "列奥纳多·达·芬奇", "科学"),
    ("21076", "几何原本", "欧几里得", "科学"),
    ("76404", "自然哲学的数学原理", "艾萨克·牛顿", "科学"),
    ("1228", "物种起源", "查尔斯·达尔文", "科学"),
    ("944", "小猎犬号航海记", "查尔斯·达尔文", "科学"),
    ("2300", "人类的由来", "查尔斯·达尔文", "科学"),
    ("30155", "相对论", "阿尔伯特·爱因斯坦", "科学"),
    ("46036", "星际信使", "伽利略·伽利雷", "科学"),
    ("14474", "蜡烛的科学", "迈克尔·法拉第", "科学"),
    ("14986", "电学实验研究", "迈克尔·法拉第", "科学"),
    ("45988", "新工具", "弗朗西斯·培根", "科学"),
    ("59058", "动物志", "亚里士多德", "科学"),
    ("57493", "自然史·卷一", "老普林尼", "科学"),
    ("2931", "人类在自然界的位置", "托马斯·赫胥黎", "科学"),
    ("4239", "人口论", "托马斯·马尔萨斯", "科学"),
    # ---- 历史 ----
    ("25717", "罗马帝国衰亡史", "爱德华·吉本", "历史"),
    ("2707", "历史·卷一", "希罗多德", "历史"),
    ("2456", "历史·卷二", "希罗多德", "历史"),
    ("7142", "伯罗奔尼撒战争史", "修昔底德", "历史"),
    ("674", "希腊罗马名人传", "普鲁塔克", "历史"),
    ("10657", "高卢战记", "尤利乌斯·凯撒", "历史"),
    ("1170", "长征记", "色诺芬", "历史"),
    ("2848", "犹太古史", "弗拉维乌斯·约瑟夫斯", "历史"),
    ("10706", "罗马史", "特奥多尔·蒙森", "历史"),
    ("1301", "法国革命史", "托马斯·卡莱尔", "历史"),
    ("10636", "马可·波罗游记·卷一", "马可·波罗", "历史"),
    ("12410", "马可·波罗游记·卷二", "马可·波罗", "历史"),
    ("8106", "库克船长航海日记", "詹姆斯·库克", "历史"),
    # ---- 哲学 ----
    ("1497", "理想国", "柏拉图", "哲学"),
    ("8438", "尼各马可伦理学", "亚里士多德", "哲学"),
    ("2680", "沉思录", "马可·奥勒留", "哲学"),
    ("59", "谈谈方法", "勒内·笛卡尔", "哲学"),
    ("4280", "纯粹理性批判", "伊曼努尔·康德", "哲学"),
    ("1998", "查拉图斯特拉如是说", "弗里德里希·尼采", "哲学"),
    ("3296", "忏悔录", "圣奥古斯丁", "哲学"),
    ("17611", "神学大全·第一部", "托马斯·阿奎那", "哲学"),
    ("3800", "伦理学", "斯宾诺莎", "哲学"),
    ("9662", "人类理解研究", "大卫·休谟", "哲学"),
    ("3330", "论语（英译）", "孔子", "哲学"),
    # ---- 社科 ----
    ("1232", "君主论", "尼可罗·马基雅维利", "社科"),
    ("3300", "国富论", "亚当·斯密", "社科"),
    ("2130", "乌托邦", "托马斯·莫尔", "社科"),
    ("34901", "论自由", "约翰·密尔", "社科"),
    ("46333", "社会契约论", "让-雅克·卢梭", "社科"),
    ("3207", "利维坦", "托马斯·霍布斯", "社科"),
    ("132", "孙子兵法（英译）", "孙武", "社科"),
    # ---- 文学 ----
    ("1727", "奥德赛", "荷马", "诗文"),
    ("6130", "伊利亚特", "荷马", "诗文"),
    ("8800", "神曲", "但丁", "诗文"),
    ("996", "堂吉诃德", "塞万提斯", "小说"),
    ("2600", "战争与和平", "列夫·托尔斯泰", "小说"),
    ("2554", "罪与罚", "陀思妥耶夫斯基", "小说"),
    ("135", "悲惨世界", "维克多·雨果", "小说"),
    ("98", "双城记", "查尔斯·狄更斯", "小说"),
    ("1342", "傲慢与偏见", "简·奥斯汀", "小说"),
    ("2701", "白鲸", "赫尔曼·梅尔维尔", "小说"),
    ("76", "哈克贝利·费恩历险记", "马克·吐温", "小说"),
    ("84", "弗兰肯斯坦", "玛丽·雪莱", "小说"),
    ("345", "德古拉", "布拉姆·斯托克", "小说"),
    ("164", "海底两万里", "儒勒·凡尔纳", "小说"),
    ("35", "时间机器", "赫伯特·威尔斯", "小说"),
    ("1661", "福尔摩斯探案集", "柯南·道尔", "小说"),
    ("14591", "浮士德", "歌德", "戏曲"),
    ("26", "失乐园", "约翰·弥尔顿", "诗文"),
    ("3600", "蒙田随笔", "蒙田", "诗文"),
    ("128", "天方夜谭", "佚名", "小说"),
]


def _get(url, timeout=90):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def html_to_text(h):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(h, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    body = soup.body or soup
    out = []
    for el in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote", "td"]):
        txt = el.get_text(" ", strip=True)
        if txt:
            out.append(txt)
            if el.name in ("h1", "h2", "h3", "h4"):
                out.append("")
    return "\n".join(out)


def download(bid):
    path = os.path.join(RAW, f"{bid}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return open(path, encoding="utf-8", errors="ignore").read()
    try:
        t = _get(f"https://www.gutenberg.org/cache/epub/{bid}/pg{bid}.txt")
    except Exception:
        t = None
        for name in (f"pg{bid}-images.html", f"pg{bid}.html"):
            try:
                t = html_to_text(_get(f"https://www.gutenberg.org/cache/epub/{bid}/{name}"))
                break
            except Exception:
                continue
        if not t:
            raise RuntimeError("no downloadable format")
    open(path, "w", encoding="utf-8").write(t)
    return t


def work(item):
    bid, zh, author, cat = item
    try:
        t = download(bid)
    except Exception as e:
        return bid, None, f"DL {e}"
    try:
        chapters, kind, words = parse(t)
    except Exception as e:
        return bid, None, f"PARSE {e}"
    return bid, {"chapters": chapters, "kind": kind, "words": words}, None


def main():
    out, fails = {}, []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, b): b for b in BOOKS}
        for f in as_completed(futs):
            bid, rec, err = f.result()
            if err:
                fails.append((bid, futs[f][1], err))
                continue
            out[bid] = rec
    for bid, zh, author, cat in BOOKS:
        r = out.get(bid)
        if not r:
            continue
        n = len(r["chapters"])
        tot = sum(len("".join(c["paras"])) for c in r["chapters"])
        print(f"{bid:>6} {zh[:20]:<22} {r['kind']} {n:>4}章 {tot:>9}字符 {r['words']:>8}词 | {r['chapters'][0]['title'][:34]}")
    print("\n失败:", fails)
    json.dump(out, open(os.path.join(SRC, "en_books.json"), "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
