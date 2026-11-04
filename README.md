# 墨读 · 公版书库

一个自托管的公版书阅读站：366 本典籍（300 本中文古籍 + 66 本西方经典，共 1.65 万节、约 3900 万字中文 / 1435 万词英文），支持英译中实时翻译、文言文白话今译、目录与书名全中文化。

**所有内容都在服务器上**：书籍正文、章节、译文、目录译名全部来自 `data/` 目录与后端接口，前端不下载整本书、不缓存书内容。译文一旦生成即写回 `data/books/*.json.gz`，成为书籍数据的一部分，重启、扩容、换设备都不会丢。浏览器只保留一个随机设备号，用于从服务端取回「读到第几章 / 最近在读」。

---

## 一、快速启动

```bash
# Python 3.11+
pip install -r requirements.txt
PORT=8000 ./start.sh
# 或
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000` 即可。无需数据库、无需构建步骤、无 Node 依赖。

Docker：

```bash
docker build -t modu-reader .
docker run -p 8000:8000 modu-reader
```

---

## 二、翻译服务配置（可选）

不做配置也能完整阅读原文，只是不显示「中文 / 白话」切换。配置后才有实时翻译能力。

任选一种方式：

**方式 A：环境变量（推荐用于容器/云平台）**

```bash
TRANSLATE_BASE_URL=https://your-endpoint/v1
TRANSLATE_API_KEY=sk-xxxx
TRANSLATE_MODEL=your-model-name
```

兼容 `OPENAI_BASE_URL` / `OPENAI_API_KEY`。任何 OpenAI Chat Completions 兼容接口都可用。

**方式 B：密钥文件**

```bash
cp .env.example .secrets/translate.json   # 然后填入真实值
```

```json
{"base_url": "https://your-endpoint/v1", "api_key": "sk-xxxx", "model": "your-model-name"}
```

> 出于安全考虑，**发布包里没有附带任何密钥文件**。密钥只在服务端读取，永远不会出现在前端代码或接口响应中。

---

## 三、目录结构

```
app.py                 FastAPI 入口：书架 / 章节 / 翻译 SSE / 阅读状态
trans.py               翻译内核：配置、分块、并发、落盘、双语提示词
requirements.txt
start.sh               启动脚本（读取 $PORT）
Dockerfile
static/
  index.html           单页外壳（不含任何书内容）
  app.js               前端逻辑
  style.css
data/
  library.json         书架索引：366 本，含分类/语种/字数/译文标志/文言系数
  books/*.json.gz      每本书的完整内容：chapters[{title,text,cn,cn_title}]
  cn_titles.json       66 本英文书的目录中文标题（4134 行）
  cn_cache/<书号>/      实时译文缓存（断点续译用，逐章 JSON）
  users/<设备号>.json   阅读进度与偏好（服务端）
tools/                 离线运维脚本（重建索引、批量译标题、同步译文等）
```

`data/` 是全部内容所在，也是最需要备份的目录。书籍文件用 gzip 存储，单本 1 KB–3 MB。

---

## 四、接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/library?q=&cat=&sort=` | 书架列表（支持搜索、分类、排序） |
| GET | `/api/stats` | 总量、分类统计 |
| GET | `/api/book/{id}` | 书籍元信息 + 目录（含中文标题） |
| GET | `/api/book/{id}/ch/{idx}` | 单章正文（原文 + 已译中文） |
| POST | `/api/book/{id}/ch/{idx}/translate` | 实时翻译，SSE 流：`meta/part/prog/done/err` |
| GET | `/api/translate/status` | 翻译服务状态、缓存统计、落盘健康度 |
| GET | `/api/cn/manifest` | 已落盘译文清单 |
| GET | `/api/cn/export?book=` | 导出译文（备份/迁移） |
| GET/PUT | `/api/state/{设备号}` | 阅读进度、最近在读、偏好（服务端存储） |

---

## 五、翻译是怎么工作的

1. 章节按 ~2600 字符 / 每块不超过 14 段切块，3 块并发请求。
2. 提示词强制模型只返回 `{"title":"…","paras":["…"]}`，段数必须与原文严格一致，不一致自动重试。
3. 英译中与文言今译是两套提示词：后者不跨语言，重点在「不加戏、不漏句、不文白夹杂」，人名官名年号照录、干支不改公历、诗句不强行散文化。
4. 每块完成即写 `data/cn_cache/<书>/<章>.json`；整章完成后由后台线程合并进 `data/books/<书>.json.gz`（原子替换 tmp → rename），并置 `has_cn`。
5. 已译章节再次打开直接读文件，实测 0.17–0.48 秒。

首次阅读未译章节仍需等待（英文 4–30 秒/章，文言 10–30 秒/章），这是按需翻译的固有成本；需要零等待可用 `tools/` 里的脚本整本预译。

---

## 六、运维脚本

| 脚本 | 用途 |
|---|---|
| `tools/merge_cn.py` | 把 `cn_cache` 里完成的译文合并进书籍文件并同步书架标志 |
| `tools/sync_cn.py` | 从线上实例拉回译文，避免重新生成 |
| `tools/translate_titles.py` | 批量翻译目录标题到 `cn_titles.json` |
| `tools/refix_titles.py` | 修复分章时被截断/合并错的标题 |
| `tools/wen_ratio.py` | 计算文言系数，决定哪些书提供今译 |
| `tools/build_v2.py` / `parse3.py` / `en_parse.py` | 从原始文本重建书库数据 |

---

## 七、数据说明

| 项目 | 数量 |
|---|---|
| 书 | 366（中文 300 / 英文 66） |
| 章节 | 16 514 |
| 中文字数 | 3 915 万 |
| 英文词数 | 1 435 万 |
| 英文书目录中文标题 | 4 134 行，覆盖 66/66 本 |
| 可白话今译的文言书 | 154 本 |
| 已生成译文 | 见 `/api/cn/manifest` |

文言书判定用字频比（`之乎者也矣焉哉…` 每千字频率 ÷ `的了着们这那…` 每千字频率），小说类阈值 3.0、其余 2.0，避免把《红楼梦》《水浒传》这类白话小说误判成文言。

---

## 八、已知限制

- 未译章节首次打开需要等待，不是 bug。
- 少数多卷本（如《罗马帝国衰亡史》）保留了原书目录页，章节顺序看起来偏长，属原书结构。
- 《封神演义》《镜花缘》等半文半白作品被阈值排除在今译之外，可在 `app.py::_can_modern` 加白名单。
