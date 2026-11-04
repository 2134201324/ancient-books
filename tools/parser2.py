#!/usr/bin/env python3
"""增强分章：回/章/卷/篇名/短标题，多候选择优"""
import re

NUM = "一二三四五六七八九十百千零〇两"
CJK = re.compile(r"[\u4e00-\u9fff]")
SENT_END = "，。！？；：、,.;:!?"


def cjk_count(s):
    return len(CJK.findall(s))


def _num(s):
    return s.replace(" ", "")


HEAD_NOISE = re.compile(r"(回中|此回|本回|上回|下回|这一回|那回|一回中)")
SEP = re.compile(r"^[-—=*·\s]{3,}$")


def is_hui(s):
    if len(s) > 46 or cjk_count(s) < 2:
        return False
    m = re.match(rf"^第\s*[{NUM}0-9]{{1,8}}\s*[回]\s*[:：]?\s*(.*)$", s)
    if not m:
        return False
    rest = m.group(1).strip()
    if rest and rest[-1] in "，。、；":
        return False
    if HEAD_NOISE.search(rest) or len(rest) > 30:
        return False
    return True


def is_zhang(s):
    if len(s) > 46 or cjk_count(s) < 2:
        return False
    m = re.match(rf"^第\s*[{NUM}0-9]{{1,8}}\s*[章节]\s*[:：]?\s*(.*)$", s)
    if not m:
        return False
    rest = m.group(1).strip()
    return not (rest and rest[-1] in "，。、；")


def is_juan(s):
    if len(s) > 40 or cjk_count(s) < 1:
        return False
    if re.match(rf"^第\s*[{NUM}0-9]{{1,6}}\s*[卷集部]", s):
        return True
    if re.match(rf"^卷\s*[{NUM}0-9]{{1,6}}", s):
        return True
    return False


GLUE = re.compile(rf"^(第\s*[{NUM}0-9]{{1,8}}\s*回[\s　]*[^。，]{{2,40}}?)(话说|却说|且说|单说|看官|原来|如今|当下|话分两头)")


def split_glued(lines):
    """把「第一回 回目 话说……」这种标题正文同行的拆开"""
    out = []
    for ln in lines:
        s = ln.rstrip()
        m = GLUE.match(s.strip())
        if m:
            head = m.group(1).strip()
            rest = s.strip()[len(head):]
            out.append(head)
            out.append(rest)
        else:
            out.append(s)
    return out


def is_titled(s):
    if len(s) > 26 or cjk_count(s) < 1:
        return False
    return bool(re.match(r"^[〈《][^〈〉《》]{1,20}[〉》]$", s))


def is_short_title(s, prev_blank, next_blank):
    """独立短标题：前后有空行、2-22 字、无句末标点"""
    if not (prev_blank and next_blank):
        return False
    if not (2 <= cjk_count(s) <= 22) or len(s) > 30:
        return False
    if s[-1] in SENT_END or s[0] in "，。！？；：、":
        return False
    if re.match(rf"^第\s*[{NUM}0-9]", s):
        return False
    return True


def enrich_titles(lines, heads, kind):
    """回目只有序号时（第X回），向后找标题行合并"""
    out = []
    for item in heads:
        i, title = item[0], item[1]
        body_start = item[2] if len(item) > 2 else i + 1
        bare = re.sub(rf"^第\s*[{NUM}0-9]{{1,8}}\s*[回章节卷集部]", "", title).strip("　 ：:")
        if not bare:
            j, steps = body_start, 0
            while j < len(lines) and steps < 10:
                s = lines[j].strip()
                if s and not SEP.match(s):
                    if 2 <= cjk_count(s) <= 24 and s[-1] not in SENT_END and not re.match(r"^(却说|话说|且说|原来|看官|如今)", s):
                        title = f"{title}　{s}"
                        body_start = j + 1
                    break
                j += 1
                steps += 1
        out.append((i, title, body_start))
    return out


def build_heads(lines):
    """返回 (kind, [(start_idx, end_idx_exclusive, title)])"""
    hui, zhang, juan, titled = [], [], [], []
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        if is_hui(s):
            hui.append((i, s))
        elif is_zhang(s):
            zhang.append((i, s))
        elif is_juan(s):
            juan.append((i, s))
        elif is_titled(s):
            titled.append((i, s))

    if len(hui) >= 4:
        return "回", enrich_titles(lines, [(i, s, i + 1) for i, s in hui], "回")
    if len(zhang) >= 4:
        return "章", enrich_titles(lines, [(i, s, i + 1) for i, s in zhang], "章")
    if len(titled) >= 4:
        return "篇", [(i, re.sub(r"^[〈《]|[〉》]$", "", s).strip(), i + 1) for i, s in titled]
    if len(juan) >= 3:
        out = []
        for i, s in juan:
            # 合并下一行的篇名
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            title = s
            end = i + 1
            if j < len(lines):
                nxt = lines[j].strip()
                if 2 <= cjk_count(nxt) <= 24 and nxt[-1] not in SENT_END and not is_hui(nxt):
                    title = f"{s}　{nxt}"
                    end = j + 1
            out.append((i, title, end))
        return "卷", enrich_titles(lines, out, "卷")
    return "单", []


def restore_paras(lines):
    paras, buf = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            if buf:
                paras.append("".join(buf)); buf = []
            continue
        if cjk_count(s) == 0 and not re.search(r"[“”「」『』〈〉《》]", s):
            continue
        if buf and s[0] in "“「『":
            paras.append("".join(buf)); buf = []
        buf.append(s)
        if s[-1] in "。！？」』”":
            paras.append("".join(buf)); buf = []
    if buf:
        paras.append("".join(buf))
    return [p for p in paras if cjk_count(p) > 0]


def parse(lines):
    lines = split_glued(lines)
    kind, heads = build_heads(lines)
    if not heads:
        return [{"title": "全文", "paras": restore_paras(lines)}], "单"

    chapters = []
    # 首个标题前的内容
    heads = [(h[0], h[1], h[2] if len(h) > 2 else h[0] + 1) for h in heads]
    pre = restore_paras(lines[:heads[0][0]])
    pre_chars = sum(cjk_count(p) for p in pre)
    if pre_chars > 800:
        chapters.append({"title": "序", "paras": pre})

    for k, (i, title, body_start) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = restore_paras(lines[body_start:end])
        if sum(cjk_count(p) for p in body) < 20:
            continue
        chapters.append({"title": title, "paras": body})
    return chapters, kind
