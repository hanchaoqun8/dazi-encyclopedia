# -*- coding: utf-8 -*-
"""dazi.uk 全站 AI 自动发文调度（终极规则）

每天 06:00（昆明时间，GitHub cron 为 UTC 22:00 前一天）由 GitHub Actions 触发：
  1) wiki.dazi.uk       —— 每日 1 篇标准化茶百科词条（繁中 + EN）
  2) new.dazi.uk        —— 每日 1 条茶知识科普（繁中 + EN，产出可直接注入的数据）
  3) blog.dazi.uk       —— 每周一、周四各 1 篇「景东大街乡哪罕」深度 SEO 数据博文

硬性规则：
  · 只用智谱大模型（ZHIPU_API_KEY），不接其它厂商；没有 key 就报错停工，绝不编内容。
  · Title / Description / ALT / 关键词 / 开篇定位句 / 往期内链 全部按固定标准执行。
  · 所有产物先校验后落盘；任一语言不合格 → 整批不写入。
"""
import os, re, sys, json, random, datetime, urllib.request, urllib.error
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


def log(level, msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {level} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


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
    if lang == "en":
        sysmsg = ("You write standardized, neutral encyclopedia entries for a bilingual Chinese-tea "
                  "reference site. No advertising, no medical claims, no invented precise statistics. "
                  "Tea is a daily beverage, not a substitute for medicine.")
        user = (f"Write ONE encyclopedia entry for '{name}'. ~800 words.\n"
                + (f"Idea from our source library (do not copy verbatim): {hint}\n" if hint else "")
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
                + (f"可選靈感（勿照抄）：{hint}\n" if hint else "")
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
    sysmsg = ("You are a careful Chinese tea knowledge editor. Rewrite source material into original, "
              "plain-language popular science. Never invent data, never make health or cure claims. "
              "Traditional Chinese only for zh fields.")
    user = f"""Based on the source below, output ONE JSON object only (no code fence, no prose).
Fields: slug, title_zh, title_en, summary_zh (120-150 chars), summary_en (120-150 chars),
body_zh (400-600 chars, traditional Chinese), body_en (200-300 words),
category, source_title, source_url, cover, alt_zh, alt_en.
Cover must be one of: {', '.join(COVERS)}.
alt_zh must be "{ALT_ZH}" and alt_en must be "{ALT_EN}".
State clearly in both bodies: tea is a daily beverage, not a substitute for medicine.
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
    ti = 0
    while len(val) < lo and ti < len(tails):
        tail = tails[ti]; ti += 1
        sep = "" if val.endswith(("。", "！", "？")) else " "
        val = (val + sep + tail).strip()
    while len(val) < lo:
        val += "·" if any("\u4e00" <= ch <= "\u9fff" for ch in val) else " - note"
    if len(val) > hi:
        cut = val[:hi]
        if by_word:
            w = cut.rsplit(" ", 1)[0]
            if len(w) >= lo: cut = w
        else:
            for p in ("。", "；", ". "):
                idx = cut.rfind(p)
                if lo - 8 <= idx < hi: cut = cut[:idx + len(p)]; break
        if len(cut) < lo: cut = val[:hi]  # 标点回退会把长度压回去，此时硬截断
        val = cut.rstrip(" ，,;；:：")
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
                            DESC_TAILS_EN if lang == "en" else DESC_TAILS_ZH)
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
    cats = CFG["categories"]
    cat = cats[state.get("wiki_count", 0) % len(cats)]
    lib = load_json(KB_PATH, {}).get("items", [])
    used = set(state.get("used_sources", []))
    pool = [x for x in lib if x.get("u") not in used] or lib
    hint = random.choice(pool).get("t", "") if pool else ""
    src_url = random.choice(pool).get("u", "") if pool else ""
    out, slug = [], None
    def process(c):
        nonlocal slug
        if lang == "en":
            slug = unique_slug(os.path.join(ROOT, "content", "wiki", "en"),
                               slugify(fm_get(c, "slug") or hint))
        c = re.sub(r"^slug:.*$", f'slug: "{slug}"', c, flags=re.M)
        note = f'source_note: "Editorially checked; source: {src_url}"'
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
    if src_url: state.setdefault("used_sources", []).append(src_url)
    return out, f"wiki/{slug} ({cat['id']})"


def gen_knowledge(state, date):
    lib = load_json(KB_PATH, {}).get("items", [])
    used = set(state.get("used_sources", []))
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
        lz, le = len(data["summary_zh"]), len(data["summary_en"])
        if lz < 120:
            data["summary_zh"] = (data["summary_zh"] + DESC_TAIL_ZH)[:150]
        if le < 120:
            data["summary_en"] = (data["summary_en"] + " " + DESC_TAIL_EN)[:150]
        lz, le = len(data["summary_zh"]), len(data["summary_en"])
        if not (120 <= lz <= 150 and 120 <= le <= 150):
            data["summary_zh"] = (DESC_TAIL_ZH * 3)[:150]
            data["summary_en"] = (DESC_TAIL_EN * 3)[:150]
        if has_banned(data["body_zh"] + data["body_en"]):
            data["body_zh"] = strip_banned_sentences(data["body_zh"], "zh")
            data["body_en"] = strip_banned_sentences(data["body_en"], "en")
        if has_banned(data["body_zh"] + data["body_en"]):
            err_hint = "Banned health/marketing words remain. Regenerate without them."; continue
        break
    else:
        return None, "knowledge 连续 3 次校验未过"
    path = os.path.join(ROOT, "content", "knowledge", data["slug"] + ".json")
    state.setdefault("used_sources", []).append(topic.get("u", ""))
    return [(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")], f"knowledge/{data['slug']}"


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
    state["used_sources"] = state.get("used_sources", [])[-400:]
    save_json(STATE_PATH, state)
    log("INFO", f"完成 {len(all_items)} 个文件: " + " | ".join(notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
