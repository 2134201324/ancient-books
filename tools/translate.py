#!/usr/bin/env python3.11
"""墨读 · 西典中文译本生成管线（可续传）

把一本英文公版书（data/books/<id>.json.gz）逐章翻译成中文，
结果写回书籍文件（章节增加 cn / cn_title 字段），并在 library.json
标记 has_cn=True。基于 OpenAI 兼容的 Chat Completions 接口，支持断点续传。

由于本环境无内置翻译密钥，本脚本用于「将来接入大模型密钥后」批量生成
其余西典的中文译本；试点书《谈谈方法》(en59) 的中文由构建阶段人工完成。

用法示例
--------
  export OPENAI_BASE_URL=https://xxx/v1
  export OPENAI_API_KEY=sk-xxx
  python3.11 tools/translate.py --book en59 \\
      --model gpt-4o-mini --books-dir data/books --lib data/library.json

断点续传：重复运行同一命令即可，已完成的章节会自动跳过。
"""
import argparse
import gzip
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("需要 requests：pip install requests")

SYS_TRANSLATE = (
    "你是一位专业的文学与学术翻译家，精通英文与简体中文。"
    "请将下面的英文文本翻译成流畅、自然、准确的简体中文，"
    "保持原意、语气与文风。务必严格保留原有的段落划分："
    "输出的段落数量必须与输入完全一致，段落之间用单个换行符(\\n)分隔，"
    "不要合并或拆分段落，不要添加任何解释、序号或前言后记。"
)
SYS_TITLE = (
    "你是一位专业翻译。请将下面的英文章节标题翻译成简洁的简体中文标题，"
    "只输出中文标题本身，不要引号、不要解释、不要序号。"
)

CHUNK_CHARS = 2600  # 每个翻译分块的最大英文字符数


def load_book(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def save_book(path, book):
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def chat(base_url, api_key, model, system, user, timeout=120):
    """调用 OpenAI 兼容接口，返回纯文本。"""
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    for attempt in range(4):
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            print(f"  ! HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        except Exception as e:  # noqa
            print(f"  ! 请求异常: {e}", file=sys.stderr)
        wait = 2 ** attempt
        print(f"  # 重试（{wait}s 后）…", file=sys.stderr)
        time.sleep(wait)
    raise RuntimeError("翻译请求失败，已达最大重试次数")


def split_chunks(paras, limit=CHUNK_CHARS):
    """把段落列表按字符数切成若干块，保持段落完整。"""
    chunks, cur, n = [], [], 0
    for p in paras:
        if n + len(p) > limit and cur:
            chunks.append(cur)
            cur, n = [], 0
        cur.append(p)
        n += len(p)
    if cur:
        chunks.append(cur)
    return chunks


def translate_chapter(base_url, api_key, model, title, text):
    paras = [p for p in text.split("\n") if p.strip()]
    cn_paras = []
    for chunk in split_chunks(paras):
        out = chat(base_url, api_key, model, SYS_TRANSLATE, "\n".join(chunk))
        got = [p for p in out.split("\n") if p.strip()]
        if len(got) != len(chunk):
            # 段落数不一致：退化为按空行合并后再均分提示，避免错位
            cn_paras.extend(got if got else chunk)
        else:
            cn_paras.extend(got)
    cn_title = chat(base_url, api_key, model, SYS_TITLE, title).strip().strip('"').strip("'")
    cn_title = re.sub(r"^[\s\d.、．]+", "", cn_title)
    return cn_title, cn_paras


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="书籍 id，如 en59")
    ap.add_argument("--books-dir", default="data/books")
    ap.add_argument("--lib", default="data/library.json")
    ap.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", ""))
    ap.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    ap.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    ap.add_argument("--force", action="store_true", help="忽略已有译文，全部重译")
    args = ap.parse_args()

    if not args.base_url or not args.api_key:
        sys.exit("请提供 --base-url / --api-key（或设置环境变量 OPENAI_BASE_URL / OPENAI_API_KEY）")

    bpath = os.path.join(args.books_dir, f"{args.book}.json.gz")
    if not os.path.exists(bpath):
        sys.exit(f"书籍文件不存在: {bpath}")
    book = load_book(bpath)
    chapters = book["chapters"]

    # 进度文件（与书籍同目录）
    prog_path = os.path.join(args.books_dir, f"{args.book}.cn.json")
    done = {}
    if os.path.exists(prog_path) and not args.force:
        try:
            done = {d["i"]: d for d in json.load(open(prog_path, encoding="utf-8"))}
            print(f"读取已有进度：{len(done)} 章已完成")
        except Exception:
            done = {}

    results = dict(done)
    for i, ch in enumerate(chapters):
        if (not args.force) and i in results and results[i].get("cn"):
            continue
        print(f"翻译 第 {i+1}/{len(chapters)} 章：{ch['title'][:50]}")
        try:
            ct, cn = translate_chapter(args.base_url, args.api_key, args.model, ch["title"], ch["text"])
            results[i] = {"i": i, "cn_title": ct, "cn": cn}
        except Exception as e:
            print(f"  !! 第 {i+1} 章失败：{e}", file=sys.stderr)
            break
        # 每章落盘，支持断点续传
        json.dump(list(results.values()), open(prog_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=0)

    # 合并进书籍文件
    ok = 0
    for i, ch in enumerate(chapters):
        if i in results and results[i].get("cn"):
            ch["cn_title"] = results[i]["cn_title"]
            ch["cn"] = results[i]["cn"]
            ok += 1
    book["has_cn"] = ok > 0
    save_book(bpath, book)

    # 更新 library.json
    if os.path.exists(args.lib):
        lib = json.load(open(args.lib, encoding="utf-8"))
        for b in lib:
            if b["id"] == args.book:
                b["has_cn"] = book["has_cn"]
        json.dump(lib, open(args.lib, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    print(f"完成：{ok}/{len(chapters)} 章已写入中文译本，has_cn={book['has_cn']}")


if __name__ == "__main__":
    main()
