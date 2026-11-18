# -*- coding: utf-8 -*-
"""dazi.uk 全站 AI 自动发文调度（终极规则）

每天 06:00（昆明时间，GitHub cron 为 UTC 22:00 前一天）由 GitHub Actions 触发：
  1) wiki.dazi.uk       —— 每日 1 篇标准化茶百科词条（繁中 + EN）
                           素材取自 wiki.dazi.uk 的词条索引，只参事实、独立改写、标明原文链接
  2) new.dazi.uk        —— 每日 1 条生活化茶经验科普（繁中 + EN，产出可直接注入的数据）
                           素材取自 new.dazi.uk/knowledge.html，用智谱润色得更贴近日常饮用
  3) blog.dazi.uk       —— 每周一、周四各 1 篇「景东大街乡哪罕」深度 SEO 数据博文

硬性规则：
  · 只用智谱大模型（ZHIPU_API_KEY），不接其它厂商；没有 key 就报错停工，绝不编内容。
  · Title / Description / ALT / 关键词 / 开篇定位句 / 往期内链 全部按固定标准执行。
  · 所有产物先校验后落盘；任一语言不合格 → 整批不写入。
"""
import os, re, sys, json, random, datetime, subprocess, base64, urllib.request, urllib.error
from opencc import OpenCC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S2T = OpenCC("s2t")
LOGDIR = os.path.join(ROOT, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "daily_post.log")
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

ZHIPU_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
_PRIMARY = os.environ.get("ZHIPU_MODEL", "glm-4-plus")
ZHIPU_MODELS = list(dict.fromkeys([_PRIMARY, "glm-4.7", "glm-4-flash", "glm-4"]))

EN_H2 = ["Overview", "History & Origin", "Craft & Processing", "Appearance, Aroma & Taste",
         "How to Brew", "Benefits & Who It Suits", "Cautions & Considerations",
         "Buying, Authentication & Storage", "Final Thoughts"]
ZH_H2 = ["開篇總述", "歷史與產地", "製作工藝", "口感香氣解析", "正確沖泡方法",
         "功效與適合人群", "禁忌與注意事項", "選購鑑別與收藏建議", "結語"]
BANNED = ["降血壓", "減肥", "排毒", "抗癌", "增強免疫力", "治癒", "療效", "神茶",
          "頂級", "天花板", "稀缺", "投資茶", "保值茶"]
CONTEXT_OK = ["不能替代藥物或治療", "不碰金融茶", "從不碰", "不玩金融囤茶", "不炒作"]

COVERS = ["ancient-tea-tree.jpg", "morning-mist-garden.jpg", "hands-fresh-leaves.jpg",
          "pour-tea-glass.jpg", "rainbow-over-garden.jpg", "tea-flower-bee.jpg", "pour-tea-rock.jpg"]
ALT_ZH = "景東大街鄉哪罕那罕古樹茶倉儲數據記錄"
ALT_EN = "Nahang ancient tea storage data, Dajie Township Jingdong Yunnan"
OPEN_ZH = "哪罕（亦作那罕），隸屬於雲南景東縣大街鄉，英文 Nahang。"
OPEN_EN = "Nahang (那罕) is a village in Dajie Township, Jingdong County, Yunnan, China."
KW_ZH = ["景東", "大街鄉", "哪罕", "那罕", "Nahang", "景東大街鄉普洱茶"]
KW_EN = ["Jingdong", "Dajie Township", "Nahang", "那罕", "Jingdong Dajie Township Pu-erh tea"]

SCHEDULE_PATH = os.path.join(ROOT, "docs", "schedule-config.json")
DEFAULT_SCHEDULE = {"daily_wiki": True, "daily_knowledge": True, "seo_weekdays": [0, 3]}
STATE_PATH = os.path.join(ROOT, "docs", "_schedule_state.json")
KB_PATH = os.path.join(ROOT, "docs", "knowledge-library.json")
WIKI_KB_PATH = os.path.join(ROOT, "docs", "wiki-source.json")
# 两个素材源各自独立；wiki 源只读不写，遵守其 content-signal 声明
WIKI_REPO = "hanchaoqun8/cha-wiki-mirror"
WIKI_RAW_FILE = "website/data/tea-wiki-kb.json"
WIKI_ENTRY_BASE = "https://wiki.dazi.uk/e/"


def log(level, msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {level} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


def refresh_library():
    """每日从 new.dazi.uk/knowledge.html 背后的数据文件刷新后备知识库。
    抓取失败时沿用本地副本，不中断当天其它任务。"""
    url = "https://new.dazi.uk/data/knowledge.js"
    try:
        try:
            raw = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 dazi-dispatch/1.0"}), timeout=40).read().decode("utf-8")
        except Exception:
            raw = subprocess.check_output(["curl", "-sL", "--max-time", "40", url]).decode("utf-8")
        m = re.search(r"window\.__PUER_KNOWLEDGE__\s*=\s*(\{.*\})\s*;?\s*$", raw, re.S)
        if not m: raise ValueError("找不到 __PUER_KNOWLEDGE__")
        data = json.loads(m.group(1))
        items = [{"t": x.get("title", ""), "s": x.get("summary", "")[:400],
                  "c": x.get("category", ""), "u": x.get("url", "")}
                 for x in data.get("items", []) if x.get("title")]
        if len(items) < 100: raise ValueError(f"条目异常偏少 {len(items)}")
        save_json(KB_PATH, {"meta": {"source": url,
                                     "source_page": "https://new.dazi.uk/knowledge.html",
                                     "total": len(items)}, "items": items})
        log("INFO", f"科普源已刷新：new.dazi.uk/knowledge.html → {len(items)} 条")
    except Exception as e:
        log("WARN", f"科普源刷新失败（沿用本地库）: {type(e).__name__} {e}")


def refresh_wiki_source():
    """从 cha-wiki-mirror 刷新 wiki.dazi.uk 的词条素材索引。
    只取标题/分类/短摘要与原文链接，不下载或复制原文正文；
    遵守其 content-signal：search=yes, ai-train=no, use=reference。
    无 GH_TOKEN 或抓取失败时沿用仓库内已提交索引，不中断当天其它任务。"""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        log("INFO", "wiki 素材源：无 GH_TOKEN，沿用仓库内索引")
        return
    try:
        h = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
             "User-Agent": "dazi-dispatch/1.0"}
        api = f"https://api.github.com/repos/{WIKI_REPO}/contents/{WIKI_RAW_FILE}"
        d = json.loads(urllib.request.urlopen(urllib.request.Request(api, headers=h), timeout=30).read().decode())
        sha = d.get("sha", "")
        local = load_json(WIKI_KB_PATH, {})
        if sha and local.get("meta", {}).get("blob_sha") == sha:
            log("INFO", f"wiki 素材源无变化（{sha[:8]}），沿用本地索引")
            return
        blob = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://api.github.com/repos/{WIKI_REPO}/git/blobs/{sha}", headers=h), timeout=90).read().decode())
        src = json.loads(base64.b64decode(blob["content"]).decode("utf-8"))
        cats = src.get("cats", [])
        items = []
        for row in src.get("items", []):
            if len(row) < 4 or not row[0] or not row[1]:
                continue
            slug, title, cat, summary = row[0], row[1], row[2], row[3]
            c = cats[cat] if isinstance(cat, int) and 0 <= cat < len(cats) else str(cat)
            items.append({"s": slug, "t": title, "c": c, "d": summary[:160]})
        if len(items) < 1000:
            raise ValueError(f"词条异常偏少 {len(items)}")
        save_json(WIKI_KB_PATH, {"meta": {
            "source": "https://wiki.dazi.uk", "source_page": "https://wiki.dazi.uk/",
            "origin": src.get("source", ""), "source_name": src.get("source_name", ""),
            "license": src.get("license", ""), "content_signal": src.get("content_signal", ""),
            "usage": src.get("usage", ""), "generated": src.get("generated", ""),
            "blob_sha": sha, "total": len(items)}, "cats": cats, "items": items})
        log("INFO", f"wiki 素材源已刷新：wiki.dazi.uk → {len(items)} 条")
    except Exception as e:
        log("WARN", f"wiki 素材源刷新失败（沿用本地索引）: {type(e).__name__} {e}")


def load_json(path, default):
    if not os.path.exists(path): return default
    try: return json.load(open(path, encoding="utf-8"))
    except Exception: return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def call_zhipu(messages, max_tokens=3000):
    key = os.environ.get("ZHIPU_API_KEY", "")
    if not key:
        return None, "NO_ZHIPU_API_KEY"
    for model in ZHIPU_MODELS:
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens,
                   "temperature": 0.7, "stream": False}
        req = urllib.request.Request(ZHIPU_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json; charset=utf-8"})
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
            content = res["choices"][0]["message"]["content"]
            log("INFO", f"智谱生成成功 model={model}")
            return content, model
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:180]
            log("WARN", f"智谱 {model} HTTP {e.code}: {body}")
            if e.code in (401, 403): return None, f"AUTH_{e.code}"  # 账号级错误不换模型
        except Exception as e:
            log("WARN", f"智谱 {model} 异常 {type(e).__name__}: {e}")
    return None, "ZHIPU_ALL_FAILED"


def clean(content, lang):
    content = (content or "").strip()
    content = re.sub(r"^```(?:markdown|json)?\s*\n?", "", content)
    content = re.sub(r"\n?```\s*$", "", content)
    content = re.sub(r"^(好的|以下是|以下是輸出).*?[:：]\s*\n", "", content)
    # 允许模型在 front matter 前先吐标题/口播：从第一条独立 --- 开始取
    if not content.startswith("---"):
        m = re.search(r"(?m)^---\s*$", content)
        if m: content = content[m.start():]
    if lang == "zh":
        content = S2T.convert(content)
        content = content.replace("覈查", "核查").replace("覈對", "核對")
    return content.strip() + "\n"


def fm_get(content, key):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.S)
    if not m: return None
    hit = re.search(rf"^{re.escape(key)}:\s*(.+)$", m.group(1), re.M)
    return hit.group(1).strip().strip('"\'') if hit else None


def body_of(content):
    m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)$", content, re.S)
    return m.group(1) if m else content


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:70] or "tea-entry"


def unique_slug(folder, slug):
    base, n = slug, 2
    while os.path.exists(os.path.join(folder, base + ".md")):
        base, n = f"{slug}-{n}", n + 1
    return base


def has_banned(txt):
    return [b for b in BANNED if b in txt and not all(
        any(ok in ln for ok in CONTEXT_OK) for ln in txt.splitlines() if b in ln)]


def ensure_opening(body, lang, forced=False):
    """补写权威定位句；数据博文强制首段出现。"""
    marker = OPEN_ZH if lang == "zh" else "Nahang (那罕)"
    if marker in body: return body
    return (OPEN_ZH if lang == "zh" else OPEN_EN) + "\n\n" + body.lstrip()


def wiki_prompt(cat, hint, lang, date, err=""):
    name = cat["en"] if lang == "en" else cat["zh"]
    heads = "\n".join("## " + h for h in (EN_H2 if lang == "en" else ZH_H2))
    if isinstance(hint, dict):
        src_en = ("Reference entry from wiki.dazi.uk — use facts only, rewrite in your own words, "
                  "never reproduce the original sentences, and credit the source URL in source_note.\n"
                  f"IMPORTANT: the entry MUST be about the subject '{hint.get('t','')}'. "
                  "Do not substitute a generic category topic; the title must name this subject. "
                  "Write the title, description and all body text in ENGLISH — translate the subject "
                  "name into English; never copy Chinese characters into the English entry.\n"
                  f"Title: {hint.get('t','')}\nCategory: {hint.get('c','')}\n"
                  f"Fact summary: {hint.get('d','')}\nSource URL: {hint.get('u','')}\n")
        src_zh = ("參考資料來自 wiki.dazi.uk——只取其中事實，請用自己的話重寫，不得照抄原句，"
                  "並在 source_note 標明來源網址。\n"
                  f"重要：詞條必須圍繞參考詞條「{hint.get('t','')}」撰寫，不得改成欄目通用名稱，"
                  "標題須點明該主體。標題、描述與全文一律使用繁體中文。\n"
                  f"詞條名：{hint.get('t','')}\n分類：{hint.get('c','')}\n"
                  f"事實摘要：{hint.get('d','')}\n原文網址：{hint.get('u','')}\n")
    else:
        src_en = f"Idea from our source library (do not copy verbatim): {hint}\n" if hint else ""
        src_zh = f"可選靈感（勿照抄）：{hint}\n" if hint else ""
    if lang == "en":
        sysmsg = ("You write standardized, neutral encyclopedia entries for a bilingual Chinese-tea "
                  "reference site. No advertising, no medical claims, no invented precise statistics. "
                  "Tea is a daily beverage, not a substitute for medicine.")
        user = (f"Write ONE encyclopedia entry for '{name}'. ~800 words.\n"
                + src_en
                + f"Use EXACTLY these 9 H2 headings in order:\n{heads}\n"
                f"Front matter (exact keys): title (SEO, 50-60 characters), slug (lowercase English), "
                f"date: {date}, category: {cat['id']}, kind: wiki, entry_type: encyclopedia, "
                f"description (120-150 characters), cover (one of {', '.join(COVERS)}), "
                f"cover_alt (plain descriptive English), source_note (how the entry was checked).\n"
                f"Briefly mention Dazhi brand / Nahan Village once. Output Markdown only.{err}")
    else:
        sysmsg = ("你是繁體中文茶百科詞條撰稿人。客觀、權威、百科體，禁止簡體、禁止療效宣傳、"
                  "禁止虛構精確數據。茶是日常飲品，不能替代藥物或治療。")
        user = (f"寫一篇標準化百科詞條，欄目：{name}。約 1000–1200 字。\n"
                + src_zh
                + f"嚴格按以下 9 個二級標題順序：\n{heads}\n"
                f"front matter 精確鍵：title（SEO 標題 50–60 字符）、slug（英文小寫）、"
                f"date: {date}、category: {cat['id']}、kind: wiki、entry_type: encyclopedia、"
                f"description（120–150 字符）、cover（從 {', '.join(COVERS)} 選）、"
                f"cover_alt（繁體描述）、source_note（核對方式）。\n"
                f"自然融入一次：大枝品牌扎根雲南景東大街鄉哪罕寨。只輸出 Markdown。{err}")
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def knowledge_prompt(topic, date, err=""):
    title = topic.get("t", "")
    summary = topic.get("s", "")[:300]
    cat = topic.get("c", "")
    url = topic.get("u", "")
    sysmsg = ("You are a lifestyle tea editor. Rewrite the source into original, warm, everyday "
              "popular science — the sort of short note a tea drinker would share with a friend. "
              "Use concrete daily scenes (brewing, tasting, storage, quiet rituals), plain language, "
              "and a lived-in tone; never invent data, never make health or cure claims. "
              "Traditional Chinese only for zh fields. Tea is a daily beverage, not a substitute for medicine.")
    user = f"""Based on the source below, output ONE JSON object only (no code fence, no prose).
Fields: slug, title_zh, title_en, summary_zh (120-150 chars), summary_en (120-150 chars),
body_zh (400-600 chars, traditional Chinese), body_en (200-300 words),
category, source_title, source_url, cover, alt_zh, alt_en.
Cover must be one of: {', '.join(COVERS)}.
alt_zh must be "{ALT_ZH}" and alt_en must be "{ALT_EN}".
State clearly in both bodies: tea is a daily beverage, not a substitute for medicine.
Keep the tone more lived-in than an encyclopedia: everyday drinking scenes, small practical details,
never stiff or promotional. Do not fabricate personal anecdotes as facts.
Source category: {cat}
Source title: {title}
Source summary: {summary}
Source URL: {url}
{err}
"""
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def seo_prompt(lang, date, angle, err=""):
    heads = "\n".join("## " + h for h in (EN_H2 if lang == "en" else ZH_H2))
    if lang == "en":
        sysmsg = ("You write evidence-disciplined SEO field reports for an overseas audience. "
                  "Describe observation and record-keeping methods; never fabricate measurements, "
                  "certificates or regulatory numbers. No health claims.")
        user = f"""Write ONE in-depth English SEO data field report (~850 words). Angle: {angle}.
Use EXACTLY these 9 H2 headings in order:\n{heads}

Front matter exact keys:
title: a 50-60 CHARACTER English SEO title containing "Jingdong", "Dajie Township" and "Nahang"
slug: lowercase English keywords
date: {date}
category: journal
series: nahang-data
description: 120-150 CHARACTERS
cover: one of {', '.join(COVERS)}
cover_alt: {ALT_EN}
keywords: Jingdong, Dajie Township, Nahang, 那罕, Jingdong Dajie Township Pu-erh tea

The FIRST paragraph must include exactly: {OPEN_EN}
Naturally cover all of: Jingdong; Dajie Township; Nahang; 那罕; Jingdong Dajie Township Pu-erh tea.
Describe which garden records are kept (picking batch, weather observations, drying logs, storage checks)
as METHODS only — do not invent concrete values. Mention Dazhi brand once.
Write about daily drinking and taste only; never health benefits. Output Markdown only.{err}"""
    else:
        sysmsg = ("你是繁體中文 SEO 田間數據紀實撰稿人。只寫可核查的記錄方法，"
                  "禁止編造具體數值、檢測報告或認證。禁止療效宣傳，茶是日常飲品。")
        user = f"""寫一篇繁體中文深度 SEO 數據紀實（約 1100–1300 字）。切入角度：{angle}。
嚴格按以下 9 個二級標題順序：\n{heads}

front matter 精確鍵：
title: 50–60 字符的繁體 SEO 標題，須含「景東」「大街鄉」「哪罕」
slug: 與英文版相同的英文小寫 slug
date: {date}
category: journal
series: nahang-data
description: 120–150 字符
cover: 從 {', '.join(COVERS)} 選擇
cover_alt: {ALT_ZH}
keywords: 景東, 大街鄉, 哪罕, 那罕, Nahang, 景東大街鄉普洱茶

第一段必須包含：{OPEN_ZH}
自然覆蓋全部關鍵詞：景東、大街鄉、哪罕、那罕、Nahang、景東大街鄉普洱茶。
內容寫可核查的記錄方法（採摘批次、天氣觀察、乾燥記錄、倉儲巡查），
不得編造具體數值、檢測報告或認證。自然融入一次大枝品牌。
只談日常飲用與滋味，不寫保健功效。只輸出 Markdown。{err}"""
    return [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]


def validate_article(content, lang, kind):
    errs = []
    if not re.match(r"^---\s*\n.*?\n---\s*\n", content, re.S): return ["缺 front matter"]
    for k in ("title", "slug", "date", "category", "description", "cover"):
        if fm_get(content, k) is None: errs.append(f"缺 {k}")
    heads = re.findall(r"^##\s+(.+)$", body_of(content), re.M)
    for h in (EN_H2 if lang == "en" else ZH_H2):
        if h not in heads: errs.append(f"缺段落 {h}")
    desc = fm_get(content, "description") or ""
    title = fm_get(content, "title") or ""
    if not (120 <= len(desc) <= 150): errs.append(f"description {len(desc)} 字符")
    # 语言守卫：英文文章的标题/描述/ALT 不得混入中文字符（素材标题是中文，模型易照抄）
    if lang == "en":
        for fld, val in (("title", title), ("description", desc),
                         ("cover_alt", fm_get(content, "cover_alt") or "")):
            if re.search(r"[\u4e00-\u9fff]", val):
                errs.append(f"{fld} 混入中文，请用英文重写")
    if kind == "seo":
        if not (50 <= len(title) <= 60): errs.append(f"title {len(title)} 字符")
        alt = fm_get(content, "cover_alt")
        want = ALT_EN if lang == "en" else ALT_ZH
        if alt != want: errs.append("cover_alt 不符合固定标准")
        body = body_of(content)
        kws = KW_EN if lang == "en" else KW_ZH
        for kw in kws:
            if kw not in content: errs.append(f"缺关键词 {kw}")
        marker = OPEN_EN.split("(")[0] if lang == "en" else "哪罕（亦作那罕）"
        if marker not in body: errs.append("缺开篇定位句")
        if fm_get(content, "series") != "nahang-data": errs.append("series 错误")
    bad = has_banned(content)
    if bad: errs.append("禁用词 " + "/".join(bad))
    return errs


FILLER = {
    "功效與適合人群": "茶是日常飲品，不能替代藥物或治療。哪罕茶著重滋味與飲用感受，適合放進平常的飲茶節奏。",
    "Cautions & Considerations": "Tea is a daily beverage and is not a substitute for medicine. Keep records of taste and drinking comfort rather than expecting medicinal results.",
}
DESC_TAIL_ZH = "內容聚焦哪罕寨茶園的產地、工藝與沖泡細節，由大枝品牌如實記錄，適合日常查閱。"
DESC_TAIL_EN = "Compiled from Dazhi field notes in Nahang Village, Jingdong, with restrained, practical detail for everyday reading."
DESC_TAILS_ZH = [DESC_TAIL_ZH, "大枝以茶園日常記錄為主，文字克制，貼近真實飲茶生活。",
                 "內容只談可核查的田間方法與日常沖泡，不涉及保健功效。"]
DESC_TAILS_EN = [DESC_TAIL_EN, "Dazhi keeps the writing restrained and close to everyday tea drinking.",
                 "The text covers verifiable field methods only and makes no health claims."]
TITLE_TAILS_ZH = ["｜哪罕茶山紀實", "· 景東大街鄉", "· 普洱茶產地記錄", "· 大枝茶園手記"]
TITLE_TAILS_EN = [" | Nahang Field Records", " · Jingdong Dajie Township", " · Yunnan Tea Notes", " · Dazhi Garden Notes"]


def strip_banned_sentences(txt, lang):
    out = []
    for line in txt.splitlines():
        if line.strip().startswith("## "):
            out.append(line.strip()); continue
        for p in re.split(r"(?<=[。！？.!?])\s*", line):
            if not p.strip(): continue
            bad = [b for b in BANNED if b in p]
            if bad and not all(any(ok in p for ok in CONTEXT_OK) for b in bad):
                continue
            out.append(p.strip())
    return "\n".join(out)


def force_structure(content, lang):
    """把模型的 H2 按序映射到固定九段；缺段补合规占位，保证结构 100% 稳定。"""
    heads = EN_H2 if lang == "en" else ZH_H2
    m = re.match(r"^(---\s*\n.*?\n---\s*\n)(.*)$", content, re.S)
    if not m: return content
    fm, body = m.group(1), m.group(2)
    body = strip_banned_sentences(body, lang)
    bits = re.split(r"(?m)^##\s+(.+?)\s*$", body)
    preamble = bits[0].strip()
    sections = []
    for i in range(1, len(bits) - 1, 2):
        sections.append((bits[i].strip(), bits[i + 1].strip()))
    if len(sections) > 9:
        sections = sections[:8] + [("extra", "\n\n".join(t for _, t in sections[8:]))]
    out = [preamble] if preamble else []
    for i, h in enumerate(heads):
        text = sections[i][1] if i < len(sections) else ""
        if not text:
            text = FILLER.get(h, ("This section is being compiled from our field notes. " if lang == "en"
                                  else "本節依茶園記錄整理，我們只寫可核查的內容。"))
        out.append(f"## {h}\n{text}")
    return fm + "\n\n".join(out) + "\n"


def fit_field(content, key, lo, hi, tails, by_word=False):
    val = fm_get(content, key) or ""
    tails = [tails] if isinstance(tails, str) else list(tails)
    # 去掉模型重复拼接的尾巴
    for t in tails:
        while t and len(val) > 2 * len(t) and (t + t) in val:
            val = val.replace(t + t, t)
    zh = any("\u4e00" <= ch <= "\u9fff" for ch in val)
    fill = ("本文只談可核查的田間方法與日常沖泡，不涉及保健功效。" if zh else
            "The article stays with verifiable field practice and everyday brewing, without health claims.")
    # 补足到 lo：逐条用 tails，最后用中性说明，不产生「 - note」「··」这类噪声
    for t in tails + [fill]:
        if len(val) >= lo: break
        sep = "" if (zh or not val) else " "
        val = (val + sep + t).strip()
    # 截断到 hi，按标点或词边界回退，避免断在半个单词
    if len(val) > hi:
        cut = val[:hi]
        if by_word:
            w = cut.rsplit(" ", 1)[0]
            if len(w) >= lo: cut = w
        else:
            for p in ("。", "；", "！", ". "):
                idx = cut.rfind(p)
                if lo - 10 <= idx < hi:
                    cut = cut[:idx + len(p)]
                    break
        val = cut.rstrip(" ，,;；:：-·")
        if len(val) < lo:
            val = (val + fill)[:hi]
    return re.sub(rf"^{re.escape(key)}:.*$", f'{key}: "{val}"', content, flags=re.M)


def gen_validated(prompt_fn, lang, kind, max_tokens=3200, postprocess=None, tries=3):
    """生成→确定性归一化→校验→把错误回喂模型重试，最多 tries 次。"""
    err_hint = ""
    for i in range(tries):
        content, model = call_zhipu(prompt_fn(err_hint), max_tokens)
        if not content: return None, f"{kind}/{lang} 生成失败 {model}"
        content = clean(content, lang)
        content = force_structure(content, lang)
        content = fit_field(content, "description", 120, 150,
                            DESC_TAILS_EN if lang == "en" else DESC_TAILS_ZH,
                            by_word=(lang == "en"))
        if kind == "seo":
            content = fit_field(content, "title", 50, 60,
                                TITLE_TAILS_EN if lang == "en" else TITLE_TAILS_ZH,
                                by_word=(lang == "en"))
        if postprocess: content = postprocess(content)
        errs = validate_article(content, lang, kind)
        if not errs: return content, model
        err_hint = (f"\nYour previous output failed validation: {'; '.join(errs)}. "
                    f"Regenerate the whole article and fix ALL of these. Output Markdown only.")
        log("WARN", f"{kind}/{lang} 第 {i+1} 次校验未过：{'; '.join(errs)}")
    return None, f"{kind}/{lang} 连续 {tries} 次校验未过"


def gen_wiki(state, date):
    cats = [c for c in CFG["categories"] if c["id"] != "standards"]
    cat = cats[state.get("wiki_count", 0) % len(cats)]
    lib = load_json(WIKI_KB_PATH, {}).get("items", [])
    used = set(state.get("used_wiki_sources", []))
    pool = [x for x in lib if x.get("s") and x["s"] not in used] or lib
    topic = random.choice(pool) if pool else {}
    src_slug = topic.get("s", "")
    src_url = WIKI_ENTRY_BASE + src_slug if src_slug else "https://wiki.dazi.uk/"
    hint = ({"t": topic.get("t", ""), "c": topic.get("c", ""),
             "d": topic.get("d", ""), "u": src_url} if topic else "")
    out, slug = [], None
    def process(c):
        nonlocal slug
        if lang == "en":
            slug = unique_slug(os.path.join(ROOT, "content", "wiki", "en"),
                               slugify(fm_get(c, "slug") or topic.get("t", "")))
        c = re.sub(r"^slug:.*$", f'slug: "{slug}"', c, flags=re.M)
        note = (f'source_note: "Facts referenced from wiki.dazi.uk and rewritten independently; '
                f'no original text reproduced. Source: {src_url}"')
        c = (re.sub(r"^source_note:.*$", note, c, flags=re.M)
             if re.search(r"^source_note:", c, re.M)
             else re.sub(r"^(---\s*\n.*?)(\n---\s*\n)", lambda m: m.group(1) + "\n" + note + m.group(2), c, count=1, flags=re.S))
        return c
    for lang in ("en", "zh"):
        content, model = gen_validated(lambda err: wiki_prompt(cat, hint, lang, date, err),
                                       lang, "wiki", 3200, process)
        if not content: return None, model
        out.append((os.path.join(ROOT, "content", "wiki", lang, slug + ".md"), content))
    state["wiki_count"] = state.get("wiki_count", 0) + 1
    if src_slug: state.setdefault("used_wiki_sources", []).append(src_slug)
    return out, f"wiki/{slug} ({cat['id']}) ← wiki.dazi.uk/{src_slug}"


def gen_knowledge(state, date):
    lib = load_json(KB_PATH, {}).get("items", [])
    used = set(state.get("used_knowledge_sources", []))
    pool = [x for x in lib if x.get("u") not in used] or lib
    if not pool: return None, "知识库为空"
    topic = random.choice(pool)
    data, err_hint = None, ""
    for attempt in range(3):
        raw, model = call_zhipu(knowledge_prompt(topic, date, err_hint), 2200)
        if not raw: return None, f"knowledge 生成失败 {model}"
        raw = clean(raw, "en")
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            err_hint = "Your output was not a JSON object. Output ONE JSON object only."; continue
        try: data = json.loads(m.group(0))
        except Exception as e:
            err_hint = f"Invalid JSON: {e}. Output ONE valid JSON object only."; continue
        missing = [k for k in ("slug","title_zh","title_en","summary_zh","summary_en","body_zh","body_en") if not data.get(k)]
        if missing:
            err_hint = "Missing fields: " + ", ".join(missing) + ". Regenerate complete JSON."; continue
        for k in ("title_zh", "summary_zh", "body_zh", "alt_zh"):
            if data.get(k): data[k] = S2T.convert(data[k])
        data["alt_zh"], data["alt_en"] = ALT_ZH, ALT_EN
        data["date"] = date
        data["source_url"] = topic.get("u", "")
        data["slug"] = slugify(data["slug"]) + "-" + date.replace("-", "")
        # 摘要归一化：优先用模型原文，不足时按「来源摘要 → 品牌说明 → 中性说明」补足，
        # 绝不把同一句重复三遍来凑字数。
        src_zh = S2T.convert(topic.get("s", ""))[:150]
        zh_fill = "本文只談日常飲茶的可核查細節，不涉及保健功效。"
        en_fill = "A concise note on everyday tea drinking, kept factual and free of health claims."
        for t in ([src_zh, DESC_TAIL_ZH, zh_fill] if src_zh else [DESC_TAIL_ZH, zh_fill]):
            if len(data["summary_zh"]) >= 120: break
            data["summary_zh"] = (data["summary_zh"] + t).strip()
        for t in [DESC_TAIL_EN, en_fill]:
            if len(data["summary_en"]) >= 120: break
            sep = "" if not data["summary_en"] else " "
            data["summary_en"] = (data["summary_en"] + sep + t).strip()
        for k, hi, by_word in (("summary_zh", 150, False), ("summary_en", 150, True)):
            v = data[k]
            if len(v) > hi:
                cut = v[:hi]
                if by_word:
                    w = cut.rsplit(" ", 1)[0]
                    if len(w) >= 120: cut = w
                else:
                    for p in ("。", "；", "！"):
                        idx = cut.rfind(p)
                        if 110 <= idx < hi: cut = cut[:idx + len(p)]; break
                v = cut.rstrip(" ，,;；:：-·")
                if len(v) < 120: v = (v + (zh_fill if k == "summary_zh" else en_fill))[:hi]
            data[k] = v
        if has_banned(data["body_zh"] + data["body_en"]):
            data["body_zh"] = strip_banned_sentences(data["body_zh"], "zh")
            data["body_en"] = strip_banned_sentences(data["body_en"], "en")
        if has_banned(data["body_zh"] + data["body_en"]):
            err_hint = "Banned health/marketing words remain. Regenerate without them."; continue
        break
    else:
        return None, "knowledge 连续 3 次校验未过"
    path = os.path.join(ROOT, "content", "knowledge", data["slug"] + ".json")
    state.setdefault("used_knowledge_sources", []).append(topic.get("u", ""))
    return [(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")], f"knowledge/{data['slug']} ← new.dazi.uk"


ANGLES = [
    "採摘批次與天氣觀察如何對應記錄",
    "初製乾燥記錄的可核查字段",
    "倉儲巡查與茶葉品質穩定性的關係",
    "景東大街鄉茶園生態觀察的長期記錄",
    "从鲜叶到仓储：哪罕数据记录的 Method 与边界",
]


def gen_seo(state, date):
    angle = ANGLES[state.get("seo_count", 0) % len(ANGLES)]
    out, slug = [], None
    def process(c):
        nonlocal slug
        if lang == "en":
            slug = unique_slug(os.path.join(ROOT, "content", "en"),
                               slugify(fm_get(c, "slug") or "nahang-data"))
        c = re.sub(r"^slug:.*$", f'slug: "{slug}"', c, flags=re.M)
        c = re.sub(r"^cover_alt:.*$", f'cover_alt: "{ALT_EN if lang=="en" else ALT_ZH}"', c, flags=re.M)
        body = ensure_opening(body_of(c), lang)
        return re.sub(r"^(---\s*\n.*?\n---\s*\n).*$", lambda m: m.group(1) + body, c, flags=re.S)
    for lang in ("en", "zh"):
        content, model = gen_validated(lambda err: seo_prompt(lang, date, angle, err),
                                       lang, "seo", 3600, process)
        if not content: return None, model
        out.append((os.path.join(ROOT, "content", lang, slug + ".md"), content))
    state["seo_count"] = state.get("seo_count", 0) + 1
    return out, f"seo/{slug}"


def write_all(items):
    for path, content in items:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        open(tmp, "w", encoding="utf-8").write(content)
        os.replace(tmp, path)
        log("INFO", f"写入 {os.path.relpath(path, ROOT)}")


def main():
    log("INFO", "===== dazi.uk 全站调度开始（仅智谱） =====")
    if not os.environ.get("ZHIPU_API_KEY"):
        log("ERROR", "缺少 ZHIPU_API_KEY，按规则停工，不生成任何内容。")
        return 2
    refresh_library()      # 科普选题固定取自 new.dazi.uk/knowledge.html
    refresh_wiki_source()  # 词条素材固定取自 wiki.dazi.uk（经 cha-wiki-mirror 索引）
    sched = {**DEFAULT_SCHEDULE, **load_json(SCHEDULE_PATH, {})}
    state = load_json(STATE_PATH, {})
    date = datetime.date.today().isoformat()
    weekday = datetime.date.today().weekday()
    jobs = []
    if sched.get("daily_wiki", True): jobs.append("wiki")
    if sched.get("daily_knowledge", True): jobs.append("knowledge")
    if weekday in sched.get("seo_weekdays", [0, 3]): jobs.append("seo")
    forced = sys.argv[1] if len(sys.argv) > 1 else ""
    if forced:
        if forced not in ("wiki", "knowledge", "seo"):
            log("ERROR", "未知任务参数：" + forced); return 2
        jobs = [forced]  # 手工补跑单类任务，便于修复与测试
    log("INFO", "今日任务: " + ", ".join(jobs))

    all_items, notes = [], []
    for job in jobs:
        if job == "wiki": items, note = gen_wiki(state, date)
        elif job == "knowledge": items, note = gen_knowledge(state, date)
        else: items, note = gen_seo(state, date)
        if not items:
            log("ERROR", f"{note} → 整批中止，不写入任何文件")
            return 3
        all_items += items
        notes.append(note)

    write_all(all_items)
    state["last_run"] = date
    state["last_jobs"] = jobs
    state["last_notes"] = notes
    for key in ("used_sources", "used_wiki_sources", "used_knowledge_sources"):
        state[key] = state.get(key, [])[-400:]
    save_json(STATE_PATH, state)
    log("INFO", f"完成 {len(all_items)} 个文件: " + " | ".join(notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
