#!/usr/bin/env python3
"""Gutenberg 中文书：下载 -> 去 PG 头尾 -> 繁转简 -> 分回 -> 段落还原 -> 校验"""
import json, os, re, sys, time, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
DATA = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(DATA, "raw")
os.makedirs(RAW, exist_ok=True)

import opencc
CC = opencc.OpenCC("t2s")

CJK = re.compile(r"[\u4e00-\u9fff]")
NUM = "一二三四五六七八九十百千零〇两"
PUNCT = "，。！？；：、"

def cjk_count(s):
    return len(CJK.findall(s))

def strip_pg(t):
    m = re.search(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\*\*\*", t, re.I)
    if m:
        t = t[m.end():]
    m = re.search(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*\*\*\*", t, re.I)
    if m:
        t = t[:m.start()]
    # 去掉文件头残留的元数据行（Produced by / Language: / Credits: 等）
    lines = t.split("\n")
    while lines:
        first = lines[0].strip()
        if not first or re.match(r"^(Produced by|Language:|Credits:|Title:|Author:|Release Date|Posting Date|Character set|Encoding|Other information|Most recently updated|Copyright)", first, re.I):
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()

def is_heading(line):
    """回目/章节标题行判定"""
    s = line.strip()
    if not s or len(s) > 46:
        return False
    if cjk_count(s) < 2:
        return False
    m = re.match(rf"^第\s*[{NUM}0-9]{{1,8}}\s*[回章节卷]\s*[:：]?\s*(.*)$", s)
    if not m:
        return False
    rest = m.group(1).strip()
    # 以逗号句号结尾 → 多半是正文句子被软换行截断
    if rest and rest[-1] in "，。、；":
        return False
    return True

def restore_paras(lines):
    """把软换行的行重组成段落。
    规则：空行断段；行尾为 。”！”？” 断段；行首为 “ 断段。
    """
    paras, buf = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            if buf:
                paras.append("".join(buf)); buf = []
            continue
        if cjk_count(s) == 0 and not re.search(r"[“”「」『』]", s):
            continue
        if buf and s[0] in "“「『":
            paras.append("".join(buf)); buf = []
        buf.append(s)
        if s[-1] in "。！？」』”":
            # 引号结尾通常是段末；但引号后若还有 "说" 类续写则不断
            paras.append("".join(buf)); buf = []
    if buf:
        paras.append("".join(buf))
    return [p for p in paras if cjk_count(p) > 0]

def parse_book(text):
    body = strip_pg(text)
    simp = CC.convert(body)
    lines = simp.split("\n")

    # 候选标题行
    heads = [(i, lines[i].strip()) for i, l in enumerate(lines) if is_heading(l)]
    kind = None
    if heads:
        # 统计"回"与"章"的数量，取多的
        hui = sum(1 for _, h in heads if "回" in h)
        zhang = sum(1 for _, h in heads if "章" in h)
        kind = "回" if hui >= zhang else "章"
        heads = [(i, h) for i, h in heads if kind in h]

    if len(heads) >= 2:
        chapters = []
        for k, (ln_i, title) in enumerate(heads):
            end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
            chunk = lines[ln_i + 1:end]
            chapters.append({"title": title, "paras": restore_paras(chunk)})
        mode = "chapter:" + kind
    else:
        # 无章节结构：按空行/标点分段，整本一章
        chapters = [{"title": "全文", "paras": restore_paras(lines)}]
        mode = "single"

    total = sum(cjk_count("".join(c["paras"])) for c in chapters)
    return {"chapters": chapters, "chars": total, "mode": mode}

def download(bid):
    path = os.path.join(RAW, f"{bid}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return open(path, encoding="utf-8", errors="ignore").read()
    url = f"https://www.gutenberg.org/cache/epub/{bid}/pg{bid}.txt"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode("utf-8", "ignore")
    open(path, "w", encoding="utf-8").write(t)
    return t

if __name__ == "__main__":
    for bid in sys.argv[1:]:
        try:
            t = download(bid)
        except Exception as e:
            print(bid, "DLFAIL", e); continue
        r = parse_book(t)
        print(f"--- {bid}: {r['mode']} 章数 {len(r['chapters'])} 汉字 {r['chars']}")
        if r["chapters"]:
            c0 = r["chapters"][0]
            print("   首:", c0["title"][:40], "| 段数", len(c0["paras"]), "| 字", cjk_count("".join(c0["paras"])))
            print("   首段:", (c0["paras"][0][:60] if c0["paras"] else ""))
            print("   末:", r["chapters"][-1]["title"][:40])
