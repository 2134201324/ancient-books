#!/usr/bin/env python3
"""中文古籍分章 v3：多模式并行 + 覆盖率择优

支持结构：
  第X回 / 第X章 / 第X卷 / 卷X      —— 章回体、史书
  【卷一  故事一】                  —— 梦溪笔谈、汉书
  学而第一 / 乃粒第一               —— 论语、天工开物（篇名+第X）
  1. 关雎                          —— 诗经、唐诗三百首
  史记 五帝本纪                     —— 史记
  魏书一　武帝纪第一                 —— 三国志
  〈篇名〉 / 《篇名》                —— 聊斋
  独立短标题（前后空行）              —— 朝花夕拾、彷徨
"""
import re

NUM = "一二三四五六七八九十百千零〇两"
CJK = re.compile(r"[\u4e00-\u9fff]")
SENT_END = "，。！？；：、,.;:!?"
SEP = re.compile(r"^[-—=*·\s]{3,}$")


def cjk_count(s):
    return len(CJK.findall(s))


# ---------------- 候选模式 ----------------
def p_hui(s):
    if len(s) > 46 or cjk_count(s) < 2:
        return None
    m = re.match(rf"^第\s*[{NUM}0-9]{{1,8}}\s*回\s*[:：]?\s*(.*)$", s)
    if not m:
        return None
    rest = m.group(1).strip()
    if rest and rest[-1] in "，。、；":
        return None
    if re.search(r"(回中|此回|本回|上回|下回|这一回|那回|一回中)", rest) or len(rest) > 30:
        return None
    return ("回", s)


def p_zhang(s):
    if len(s) > 46 or cjk_count(s) < 2:
        return None
    m = re.match(rf"^第\s*[{NUM}0-9]{{1,8}}\s*[章节出折幕场]\s*[:：]?\s*(.*)$", s)
    if not m:
        return None
    rest = m.group(1).strip()
    if rest and rest[-1] in "，。、；":
        return None
    return ("章", s)


def p_juan(s):
    if len(s) > 44 or cjk_count(s) < 1:
        return None
    if re.match(rf"^第\s*[{NUM}0-9]{{1,6}}\s*[卷集部]", s):
        return ("卷", s)
    if re.match(rf"^卷\s*[{NUM}0-9]{{1,6}}", s):
        return ("卷", s)
    return None


def p_bracket(s):
    m = re.match(r"^【\s*(.{1,32}?)\s*】$", s)
    if not m:
        m = re.match(r"^〔\s*(.{1,32}?)\s*〕$", s)
    if not m:
        return None
    t = m.group(1).strip()
    if cjk_count(t) < 1:
        return None
    return ("卷", t)


def p_pian(s):
    """学而第一 / 乃粒第一 / 逍遥游第一"""
    if len(s) > 16 or cjk_count(s) < 2:
        return None
    m = re.match(rf"^([\u4e00-\u9fff]{{2,6}})第([{NUM}]{{1,3}})$", s)
    if not m:
        return None
    return ("篇", s)


def p_num(s):
    """1. 关雎 / 12、某项"""
    if len(s) > 30:
        return None
    m = re.match(r"^(\d{1,3})\s*[.、．]\s*(.{1,24})$", s)
    if not m:
        return None
    t = m.group(2).strip()
    if cjk_count(t) < 1 or t[-1] in "。，；":
        return None
    if any(ch in t for ch in "：:「」『』〔〕（）"):
        return None
    return ("篇", t)


def p_shiji(s):
    m = re.match(r"^史记\s+([\u4e00-\u9fff]{2,14})$", s)
    if m:
        return ("篇", m.group(1))
    return None


def p_sanguo(s):
    m = re.match(rf"^(魏书|蜀书|吴书|晋书)\s*([{NUM}]{{1,3}})\s*([\u4e00-\u9fff]{{1,12}}第[{NUM}]{{1,3}})$", s)
    if m:
        return ("卷", f"{m.group(1)} {m.group(2)}　{m.group(3)}")
    return None


def p_brackets_title(s):
    if len(s) > 30 or cjk_count(s) < 1:
        return None
    m = re.match(r"^[〈《]([^〈〉《》]{1,22})[〉》]$", s)
    if m:
        return ("篇", m.group(1).strip())
    return None


def p_bullet(s):
    """●卷一 / ○三易 —— 日知录式项目符号标题"""
    m = re.match(r"^[●○◎◇◆◉]\s*(.{1,24})$", s)
    if not m:
        return None
    t = m.group(1).strip()
    if cjk_count(t) < 1 or t[-1] in "。，；":
        return None
    return ("卷" if re.match(rf"^第?\s*[{NUM}0-9]{{1,3}}\s*[卷集部]", t) else "篇", t)


def p_zuozhuan(s):
    """隐公元年 / 桓公二年 —— 左传、公羊、谷梁"""
    m = re.match(r"^(隐|桓|庄|闵|僖|文|宣|成|襄|昭|定|哀|悼)公(元|[一二三四五六七八九十]{1,3})年$", s)
    if m:
        return ("篇", s)
    return None


def p_numonly(s):
    """单独一行的『一』『二』『三』—— 现代小说分节"""
    if cjk_count(s) != 1 or s not in "一二三四五六七八九十":
        return None
    return ("节", s)


PATTERNS = [
    ("回", p_hui), ("章", p_zhang), ("卷", p_juan), ("卷", p_bracket),
    ("篇", p_pian), ("篇", p_num), ("篇", p_shiji), ("卷", p_sanguo),
    ("篇", p_brackets_title), ("卷", p_bullet), ("篇", p_zuozhuan),
    ("节", p_numonly),
]

# 人工校准：book id -> [(kind, regex)]，用于结构特殊、通用规则抓不到的书
OVERRIDE = {
    "25273": [("篇", r"^([\u4e00-\u9fff]{2,5})第[一二三四五六七八九十]{1,3}$")],   # 天工开物
    "23876": [("篇", r"^(后?游[\u4e00-\u9fff]{2,8}日记|[\u4e00-\u9fff]{1,6}游日记[一二三四五六七八九十]?)$")],
    "23873": [("篇", r"^\d{1,3}\s*[.、．]\s*([\u4e00-\u9fff]{1,12})$")],           # 诗经
    "52323": [("篇", r"^(\d{1,3})$")],                                              # 唐诗三百首
    "20968": [("篇", r"^(\d{1,3})$")],
    "25242": [("篇", r"^[\u4e00-\u9fff]{2,12}$")],                                # 野草（短标题）
}


def build_heads(lines, pats):
    heads = []
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or len(s) > 60:
            continue
        for kind, fn in pats:
            r = fn(s)
            if r:
                heads.append((i, r[1], kind))
                break
    return heads


def split_glued(lines):
    """「第一回 回目 话说……」标题正文同行"""
    out = []
    glue = re.compile(rf"^(第\s*[{NUM}0-9]{{1,8}}\s*回[\s　]*[^。，]{{2,40}}?)(话说|却说|且说|单说|看官|原来|如今|当下|话分两头)")
    for ln in lines:
        s = ln.rstrip()
        m = glue.match(s.strip())
        if m:
            head = m.group(1).strip()
            out.append(head)
            out.append(s.strip()[len(head):])
        else:
            out.append(s)
    return out


def restore_paras(lines, latin=False):
    """软换行还原段落"""
    paras, buf = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            if buf:
                paras.append((" " if latin else "").join(buf) if latin else "".join(buf))
                buf = []
            continue
        if not latin and cjk_count(s) == 0 and not re.search(r"[“”「」『』〈〉《》]", s):
            continue
        if buf:
            if (not latin and s[0] in "“「『") or (not latin and re.match(r"^\d{1,3}[.、．]", s)):
                paras.append("".join(buf))
                buf = []
            elif latin and len(" ".join(buf)) > 900:
                paras.append(" ".join(buf))
                buf = []
        buf.append(s)
        if s[-1] in "。！？」』”" or (latin and s[-1] in '.!?"”'):
            paras.append((" " if latin else "").join(buf) if latin else "".join(buf))
            buf = []
        elif not latin and len("".join(buf)) > 700:
            paras.append("".join(buf))
            buf = []
    if buf:
        paras.append((" " if latin else "").join(buf) if latin else "".join(buf))
    return [p for p in paras if (len(p) > 0 if latin else cjk_count(p) > 0)]


def chapters_from_heads(lines, heads):
    # 纯数字标题（001 / 12）向后合并一行书名或诗题
    fixed = []
    for i, title, k in heads:
        if re.fullmatch(r"\d{1,4}", title):
            j = i + 1
            while j < len(lines) and not lines[j].strip() and j < i + 4:
                j += 1
            if j < len(lines):
                nxt = lines[j].strip()
                if 0 < len(nxt) <= 24 and nxt[-1] not in SENT_END:
                    fixed.append((i, f"{title}　{nxt}", k, j + 1))
                    continue
        fixed.append((i, title, k, i + 1))
    heads = fixed

    out = []
    pre = restore_paras(lines[:heads[0][0]])
    if sum(cjk_count(p) for p in pre) > 800:
        out.append({"title": "序", "paras": pre})
    for k, (i, title, _k, start) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = restore_paras(lines[start:end])
        if sum(cjk_count(p) for p in body) < 25:
            continue
        out.append({"title": title, "paras": body})
    return out


def coverage(chapters):
    """返回 (覆盖率, 章节数)：覆盖率只统计长度合理的章节"""
    if len(chapters) < 2:
        return 0.0, 0
    total = sum(sum(cjk_count(p) for p in c["paras"]) for c in chapters)
    if total <= 0:
        return 0.0, 0
    lo = max(35, min(400, int(total * 0.0004)))
    good = [c for c in chapters if lo <= sum(cjk_count(p) for p in c["paras"]) <= 60000]
    return sum(sum(cjk_count(p) for p in c["paras"]) for c in good) / total, len(good)


def parse(lines, bid=None):
    lines = split_glued(lines)
    best, best_s, best_kind = None, 0.0, "单"

    cands = []
    pats = list(PATTERNS)
    if bid and bid in OVERRIDE:
        extra = []
        for kind, rgx in OVERRIDE[bid]:
            rx = re.compile(rgx)

            def mk(rx=rx, kind=kind):
                def f(s):
                    m = rx.match(s)
                    if not m:
                        return None
                    return (kind, m.group(1).strip() if m.groups() else s)
                return f
            extra.append((kind, mk()))
        pats = extra + pats
    for kind, fn in pats:
        hs = []
        for i, raw in enumerate(lines):
            s = raw.strip()
            if not s or len(s) > 60:
                continue
            r = fn(s)
            if r:
                hs.append((i, r[1], r[0]))
        cands.append((kind, hs))

    scored = []
    for kind, hs in cands:
        if len(hs) < 3:
            continue
        chs = chapters_from_heads(lines, hs)
        cov, _ngood = coverage(chs)
        if cov < 0.55:
            continue
        scored.append((cov, len(chs), kind, chs))

    if scored:
        top = max(c[0] for c in scored)
        # 覆盖率相近时优先更细的切分
        pool = [c for c in scored if c[0] >= top - 0.05]
        best = max(pool, key=lambda c: c[1])
        return best[3], best[2]
    return [{"title": "全文", "paras": restore_paras(lines)}], "单"


def fallback_split(lines, target=6000):
    """无结构长文本：按段落切成等长小节"""
    paras = restore_paras(lines)
    if not paras:
        return [{"title": "全文", "paras": []}]
    out, buf, n = [], [], 0
    for p in paras:
        buf.append(p)
        n += cjk_count(p)
        if n >= target:
            out.append({"title": f"第 {len(out)+1} 节", "paras": buf})
            buf, n = [], 0
    if buf:
        out.append({"title": f"第 {len(out)+1} 节", "paras": buf})
    return out
