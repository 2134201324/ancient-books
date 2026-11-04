#!/usr/bin/env python3
"""站点数据总构建：中文古籍 + 西方典籍 -> 分类 -> library.json + books/*.json.gz"""
import gzip
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import strip_pg, CC
from parse3 import parse, fallback_split, cjk_count
from build_en import BOOKS as EN_BOOKS

SRC = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(SRC, "raw")
DST = "/workspace/gutenberg-reader/data"
BOOKS_DIR = os.path.join(DST, "books")
os.makedirs(BOOKS_DIR, exist_ok=True)

AUTHOR_MAP = {'史记': '司马迁', '汉书': '班固', '后汉书': '范晔', '三国志': '陈寿', '宋史': '脱脱等', '资治通鉴': '司马光', '左传': '左丘明', '战国策': '刘向 编', '国语': '左丘明', '论语': '孔子及弟子', '孟子': '孟子', '老子': '老子', '庄子': '庄周', '韩非子': '韩非', '墨子': '墨翟', '荀子': '荀况', '管子': '管仲', '淮南子': '刘安', '列子': '列御寇', '论衡': '王充', '日知录': '顾炎武', '明夷待访录': '黄宗羲', '传习录': '王阳明', '王阳明全集': '王阳明', '张载集': '张载', '呻吟语': '吕坤', '菜根谭': '洪应明', '幽梦影': '张潮', '世说新语': '刘义庆', '山海经': '佚名', '徐霞客游记': '徐霞客', '水经注': '郦道元', '东京梦华录': '孟元老', '洛阳伽蓝记': '杨衒之', '梦溪笔谈': '沈括', '天工开物': '宋应星', '伤寒论': '张仲景', '本草备要': '汪昂', '脾胃论': '李杲', '周髀算经': '佚名', '孙子算经': '佚名', '茶经': '陆羽', '齐民要术': '贾思勰', '诗经': '佚名', '楚辞': '屈原等', '唐诗三百首': '蘅塘退士 编', '李太白集': '李白', '古文观止': '吴楚材 吴调侯', '文心雕龙': '刘勰', '人间词话': '王国维', '随园诗话': '袁枚', '陶庵梦忆': '张岱', '浮生六记': '沈复', '朝花夕拾': '鲁迅', '呐喊': '鲁迅', '彷徨': '鲁迅', '野草': '鲁迅', '南腔北调集': '鲁迅', '长生殿': '洪昇', '桃花扇': '孔尚任', '牡丹亭': '汤显祖', '西厢记': '王实甫', '琵琶记': '高明', '窦娥冤': '关汉卿', '盐铁论': '桓宽', '商君书': '商鞅', '六韬': '姜尚', '尉缭子': '尉缭', '孙子兵法': '孙武', '鬼谷子': '鬼谷子', '幼学琼林': '程登吉', '尔雅': '佚名', '方言': '扬雄', '贞观政要': '吴兢', '列女传': '刘向', '新序': '刘向', '说苑': '刘向', '韩诗外传': '韩婴', '吴越春秋': '赵晔', '越绝书': '袁康', '竹书纪年': '佚名', '颜氏家训': '颜之推', '近思录': '朱熹 吕祖谦', '朱子语类': '黎靖德 编', '大学': '曾子', '中庸': '子思', '礼记': '佚名', '周礼': '佚名', '仪礼': '佚名', '易经': '佚名', '周易': '佚名', '六祖坛经': '慧能', '金刚经': '鸠摩罗什 译', '抱朴子': '葛洪', '黄帝宅经': '佚名', '三字经': '王应麟', '百家姓': '佚名', '千字文': '周兴嗣', '说文解字': '许慎', '康熙字典': '张玉书等', '文渊阁四库全书': '纪昀等', '池北偶谈': '王士禛', '南部新书': '钱易', '北梦琐言': '孙光宪', '鸡肋编': '庄绰', '竹叶亭杂记': '姚元之', '续世说': '孔平仲', '拾遗记': '王嘉', '幽明录': '刘义庆', '搜神记': '干宝', '杜骗新书': '张应俞', '聊斋志异': '蒲松龄', '红楼梦': '曹雪芹', '三国演义': '罗贯中', '水浒传': '施耐庵', '西游记': '吴承恩', '金瓶梅': '兰陵笑笑生', '儒林外史': '吴敬梓', '镜花缘': '李汝珍', '官场现形记': '李伯元', '老残游记': '刘鹗', '封神演义': '许仲琳', '今古奇观': '抱瓮老人 编', '喻世明言': '冯梦龙', '警世通言': '冯梦龙', '醒世恒言': '冯梦龙', '初刻拍案惊奇': '凌濛初', '二刻拍案惊奇': '凌濛初', '闲情偶寄': '李渔', '十二楼': '李渔', '无声戏': '李渔', '豆棚闲话': '艾衲居士', '阅微草堂笔记': '纪昀', '子不语': '袁枚', '文选': '萧统 编', '乐府诗集': '郭茂倩 编', '花间集': '赵崇祚 编', '诗品': '钟嵘'}
META = json.load(open(os.path.join(SRC, "meta.json"), encoding="utf-8"))
RAW_LIST = {x["id"]: x for x in json.load(open(os.path.join(SRC, "raw_list.json"), encoding="utf-8"))}

# ---------------- 分类 ----------------
def classify(title, subs, kind="单"):
    s = " | ".join(subs).lower()
    t = title

    # 书名硬规则（优先于元数据）
    HARD = {
        "戏曲": ["西厢记", "牡丹亭", "长生殿", "桃花扇", "琵琶记", "窦娥冤", "汉宫秋", "救风尘",
                 "倩女离魂", "邯郸记", "紫钗记", "南柯记", "风筝误", "十五贯", "白兔记", "拜月亭"],
        "科学": ["天工开物", "梦溪笔谈", "伤寒论", "本草", "黄帝内经", "周髀算经", "孙子算经",
                 "九章算术", "齐民要术", "农政全书", "营造法式", "洗冤集录", "茶经", "酒经",
                 "数书九章", "海岛算经", "脉经", "针灸", "千金方", "脾胃论", "难经", "素问"],
        "蒙学": ["三字经", "百家姓", "千字文", "幼学琼林", "增广贤文", "声律启蒙", "说文解字",
                 "康熙字典", "尔雅", "方言", "释名", "广韵"],
        "哲学": ["论语", "孟子", "大学", "中庸", "老子", "道德经", "庄子", "列子", "墨子", "荀子",
                 "韩非子", "管子", "淮南子", "传习录", "王阳明", "近思录", "朱子", "二程", "陆九渊",
                 "六祖坛经", "金刚经", "法华经", "楞严经", "圆觉经", "四十二章经", "抱朴子",
                 "论衡", "日知录", "明夷待访录", "周易", "易经", "易传", "春秋繁露", "法言",
                 "中说", "颜氏家训", "菜根谭", "呻吟语", "幽梦影", "小窗幽记", "围炉夜话",
                 "张载集", "二程集", "朱子语类", "象山", "太极图", "通书", "正蒙"],
        "历史": ["史记", "汉书", "后汉书", "三国志", "晋书", "宋书", "南齐书", "梁书", "陈书",
                 "魏书", "北齐书", "周书", "隋书", "南史", "北史", "旧唐书", "新唐书", "旧五代史",
                 "新五代史", "宋史", "辽史", "金史", "元史", "明史", "清史稿", "资治通鉴",
                 "左传", "公羊传", "谷梁传", "战国策", "国语", "吴越春秋", "越绝书", "竹书纪年",
                 "徐霞客游记", "山海经", "水经注", "东京梦华录", "洛阳伽蓝记", "大唐西域记",
                 "世说新语", "续世说", "贞观政要", "通典", "文献通考", "列女传", "新序", "说苑",
                 "韩诗外传", "吴船录", "瀛涯胜览", "裨海纪游", "台湾外纪", "天妃显圣录"],
        "诗文": ["诗经", "楚辞", "唐诗三百首", "全唐诗", "李太白集", "杜工部", "白居易", "王维",
                 "孟浩然", "李商隐", "杜牧", "苏轼", "东坡", "稼轩", "李清照", "纳兰", "古文观止",
                 "文心雕龙", "人间词话", "随园诗话", "诗品", "沧浪诗话", "昭明文选", "玉台新咏",
                 "乐府诗集", "花间集", "陶庵梦忆", "西湖梦寻", "浮生六记", "朝花夕拾", "野草",
                 "彷徨", "呐喊", "沉沦", "南腔北调", "华盖集", "而已集", "三闲集", "二心集",
                 "伪自由书", "准风月谈", "花边文学", "且介亭", "集外集", "故事新编"],
        "社科": ["孙子兵法", "吴子", "六韬", "三略", "司马法", "尉缭子", "三十六计", "商君书",
                 "韩非子", "盐铁论", "大学衍义", "明夷待访录"],
        "小说": ["红楼梦", "三国演义", "水浒", "西游记", "金瓶梅", "儒林外史", "聊斋", "镜花缘",
                 "官场现形记", "老残游记", "二十年目睹", "孽海花", "封神演义", "东周列国",
                 "隋唐演义", "说岳全传", "儿女英雄传", "三侠五义", "施公案", "狄公案",
                 "今古奇观", "三言", "二拍", "喻世明言", "警世通言", "醒世恒言", "初刻拍案",
                 "二刻拍案", "十二楼", "连城璧", "无声戏", "肉蒲团", "灯草和尚", "株林野史",
                 "豆棚闲话", "醉醒石", "照世杯", "五色石", "八段锦", "恨海", "二十年目睹之怪现状"],
    }
    for cat, keys in HARD.items():
        if any(k in t for k in keys):
            return cat

    if re.search(r"fiction|novel|tales|short stories|legends|ghost stories|folklore|fantasy|detective|erotic", s):
        return "小说"
    if "drama" in s:
        return "戏曲"
    if "military" in s:
        return "社科"
    if re.search(r"science|mathematic|medicine|technology|astronomy|arithmetic|natural history|engineering|chemistry|physics", s):
        return "科学"
    if re.search(r"history|description and travel|geography|antiquit|biography|diaries|sources", s):
        return "历史"
    if re.search(r"philosophy|taoism|buddhism|zen|ethics|confucian|conduct of life|neo-confucianism|religion|divination", s):
        return "哲学"
    if re.search(r"politics|government|military|law|economic|political", s):
        return "社科"
    if re.search(r"poetry|poems|ci \(chinese poetry\)|prose|essays|literature|criticism", s):
        return "诗文"
    if re.search(r"readers|language|names, personal|bibliograph|dictionar", s):
        return "蒙学"
    if kind == "回":
        return "小说"
    if re.search(r"chinese classics|text", s):
        return "诗文"
    return "其他"


def chapter_no(title):
    DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}
    UNIT = {"十": 10, "百": 100, "千": 1000}
    m = re.match(r"^第\s*([一二三四五六七八九十百千零〇两0-9]{1,8})\s*回", title)
    if not m:
        return None
    s = m.group(1)
    if s.isdigit():
        return int(s)
    if all(c in DIGIT for c in s):
        v = "".join(str(DIGIT[c]) for c in s)
        return int(v) if v else None
    total, cur = 0, 0
    for c in s:
        if c in DIGIT:
            cur = DIGIT[c]
        elif c in UNIT:
            if cur == 0:
                cur = 1
            total += cur * UNIT[c]
            cur = 0
        else:
            return None
    return total + cur


def work_cn(bid):
    path = os.path.join(RAW, f"{bid}.txt")
    if not os.path.exists(path):
        return None
    try:
        body = CC.convert(strip_pg(open(path, encoding="utf-8", errors="ignore").read()))
        chapters, kind = parse(body.split("\n"), bid)
        chars = sum(cjk_count(p) for c in chapters for p in c["paras"])
        if kind == "单" and chars > 20000:
            chapters = fallback_split(body.split("\n"), 8000)
            kind = "节"
        return bid, chapters, kind, chars
    except Exception as e:
        print("ERR", bid, e)
        return None


def main():
    ids = [k for k in RAW_LIST if os.path.exists(os.path.join(RAW, f"{k}.txt"))]
    res = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(work_cn, b) for b in ids]):
            r = f.result()
            if r:
                res[r[0]] = r
    print("解析完成", len(res))

    records = {}
    for bid, chapters, kind, chars in res.values():
        if chars < 6000:
            continue
        subs = META.get(bid, [])
        b = RAW_LIST[bid]
        title = re.sub(r"\s*\(Chinese\)\s*$", "", b["title"]).strip()
        title = re.sub(r"[\s　]*Volume\s*[\d\-–—]+$", "", title, flags=re.I).strip()
        title = CC.convert(title)
        nums = [n for n in (chapter_no(c["title"]) for c in chapters) if n]
        missing, last = 0, 0
        if len(nums) > 2:
            nums = sorted(set(nums))
            last = nums[-1]
            missing = (last - nums[0] + 1) - len(nums)
        complete = (missing <= max(3, last * 0.05)) if last else True
        rec = {
            "id": bid, "title": title, "author": AUTHOR_MAP.get(title) or b["author"],
            "chars": chars, "words": 0, "n": len(chapters), "kind": kind,
            "lang": "zh", "cat": classify(title, subs, kind),
            "ok": complete, "subject": [x for x in subs if x != "Text"][:3],
            "chapters": [{"title": c["title"], "text": "\n".join(c["paras"])} for c in chapters],
        }
        old = records.get(title)
        if not old or rec["chars"] > old["chars"]:
            records[title] = rec

    # 分卷合并（粉妆楼 1-10 / 11-20，搜神记 volume 4-10）
    SPLIT = re.compile(r"^(.+?)\s*(\d+)\s*[-–—]\s*(\d+)\s*(回|卷|章)?$")
    groups = {}
    for t, rec in list(records.items()):
        m = SPLIT.match(t)
        if m:
            groups.setdefault(m.group(1).strip(), []).append((int(m.group(2)), rec, t))
    for base, arr in groups.items():
        if len(arr) < 2:
            continue
        arr.sort(key=lambda x: x[0])
        merged, seen = [], set()
        for _, rec, t in arr:
            for ch in rec["chapters"]:
                if ch["title"] in seen:
                    continue
                seen.add(ch["title"])
                merged.append(ch)
            records.pop(t, None)
        head = min(arr, key=lambda x: x[0])[1]
        records[base] = dict(head, title=base, chapters=merged, n=len(merged),
                             chars=sum(r["chars"] for _, r, _ in arr), ok=True)

    # 标题互相包含时保留更完整的
    names = sorted(records.keys(), key=len)
    for short in names:
        for long in list(records.keys()):
            if long == short or short not in records or long not in records:
                continue
            if short in long and records[long]["n"] >= records[short]["n"]:
                records.pop(short, None)
                break

    library = []
    for rec in records.values():
        with gzip.open(os.path.join(BOOKS_DIR, f"{rec['id']}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        library.append({k: v for k, v in rec.items() if k != "chapters"})

    # ---------------- 西方典籍 ----------------
    en = json.load(open(os.path.join(SRC, "en_books.json"), encoding="utf-8"))
    for bid, zh, author, cat in EN_BOOKS:
        r = en.get(bid)
        if not r:
            continue
        chs = r["chapters"]
        chars = sum(len(p) for c in chs for p in c["paras"])
        rec = {
            "id": "en" + bid, "title": zh, "author": author,
            "chars": chars, "words": r["words"], "n": len(chs), "kind": r["kind"],
            "lang": "en", "cat": cat, "ok": True, "subject": [],
            "chapters": [{"title": c["title"], "text": "\n".join(c["paras"])} for c in chs],
        }
        with gzip.open(os.path.join(BOOKS_DIR, f"{rec['id']}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        library.append({k: v for k, v in rec.items() if k != "chapters"})

    library.sort(key=lambda x: -x["chars"])
    json.dump(library, open(os.path.join(DST, "library.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # 清理已不存在的书
    keep = {b["id"] for b in library}
    for f in os.listdir(BOOKS_DIR):
        if f.split(".")[0] not in keep:
            os.remove(os.path.join(BOOKS_DIR, f))

    size = sum(os.path.getsize(os.path.join(BOOKS_DIR, f)) for f in os.listdir(BOOKS_DIR))
    print(f"共 {len(library)} 本 | 汉字 {sum(x['chars'] for x in library)/1e6:.1f}M | 磁盘 {size/1024/1024:.1f}MB")
    print(Counter(x["cat"] for x in library))
    print(Counter(x["kind"] for x in library))
    print(Counter(x["lang"] for x in library))


if __name__ == "__main__":
    main()
