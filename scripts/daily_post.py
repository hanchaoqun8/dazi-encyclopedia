# -*- coding: utf-8 -*-
"""每日自動生成一篇雙語茶百科文章（EN + 繁中）
選題來源：docs/knowledge-library.json（474篇後備知識庫）+ 7大欄目輪換。
模型：智譜優先，魔搭回退（模型池自動跳過下線者）。
兜底：API 全不可用 → 寫告警日志停止，不亂編。
"""
import os, re, sys, json, datetime, urllib.request, urllib.error
from opencc import OpenCC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S2T = OpenCC("s2t")
LOGDIR = os.path.join(ROOT, "logs")
os.makedirs(LOGDIR, exist_ok=True)
LOG = os.path.join(LOGDIR, "daily_post.log")
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

ZHIPU_MODELS = ["glm-4-plus", "glm-4.7", "glm-4-flash", "glm-4"]
MS_MODELS = ["Qwen/Qwen3.5-27B", "Qwen/Qwen3.8-Flash-Next", "ZhipuAI/GLM-4.7-Flash",
             "Qwen/Qwen2.5-7B-Instruct", "internlm/internlm2_5-7b-chat"]

EN_H2 = ["Overview","History & Origin","Craft & Processing","Appearance, Aroma & Taste",
         "How to Brew","Benefits & Who It Suits","Cautions & Considerations",
         "Buying, Authentication & Storage","Final Thoughts"]
ZH_H2 = ["開篇總述","歷史與產地","製作工藝","口感香氣解析","正確沖泡方法",
         "功效與適合人群","禁忌與注意事項","選購鑑別與收藏建議","結語"]
BRAND_CN = ("雲南景東哪罕一帶，山林氣候溫潤，茶樹生長節奏慢，茶葉更容易積累層次豐富的香氣與湯感。"
            "大枝品牌扎根哪罕寨，始終關注源頭茶園的生態狀態與茶葉本味。")


def log(level, msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {level} {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


def call_llm(messages, max_tokens=3000):
    zp, ms = os.environ.get("ZHIPU_API_KEY", ""), os.environ.get("MODELSCOPE_API_KEY", "")
    providers = []
    if zp: providers.append(("zhipu", "https://open.bigmodel.cn/api/paas/v4/chat/completions", zp, ZHIPU_MODELS))
    if ms: providers.append(("modelscope", "https://api-inference.modelscope.cn/v1/chat/completions", ms, MS_MODELS))
    if not providers: return None, "NO_API_KEY"
    for name, url, key, models in providers:
        for model in models:
            payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.8}
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers={
                "Authorization": "Bearer " + key, "Content-Type": "application/json; charset=utf-8"})
            try:
                r = urllib.request.urlopen(req, timeout=90)
                res = json.loads(r.read().decode())
                content = res["choices"][0]["message"]["content"]
                log("INFO", f"模型成功 {name}/{model}")
                return content, model
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:160]
                log("WARN", f"{name}/{model} HTTP {e.code}: {body}")
                if e.code in (401, 403): break
            except Exception as e:
                log("WARN", f"{name}/{model} 異常 {type(e).__name__}")
    return None, "ALL_FAILED"


def pick_topic():
    """輪換欄目 + 從知識庫取一個相關條目作靈感。"""
    state_path = os.path.join(ROOT, "docs", "_topic_state.json")
    idx = 0
    if os.path.exists(state_path):
        idx = json.load(open(state_path, encoding="utf-8")).get("last", -1) + 1
    cats = CFG["categories"]
    cat = cats[idx % len(cats)]
    json.dump({"last": idx}, open(state_path, "w", encoding="utf-8"))
    # 知識庫靈感
    kb_path = os.path.join(ROOT, "docs", "knowledge-library.json")
    topic_hint = ""
    if os.path.exists(kb_path):
        lib = json.load(open(kb_path, encoding="utf-8"))
        cat_name = cat["zh"]
        hits = [x for x in lib.get("items", []) if cat_name[:2] in x.get("c", "") or cat["en"][:3].lower() in x.get("t", "").lower()]
        if hits:
            import random
            topic_hint = random.choice(hits[:20]).get("t", "")
    return cat, topic_hint


def build_prompt(cat, topic_hint, lang, date_str):
    name = cat["en"] if lang == "en" else cat["zh"]
    heads = EN_H2 if lang == "en" else ZH_H2
    head_block = "\n".join("## " + h for h in heads)
    if lang == "en":
        return [
            {"role": "system", "content": "You are a professional Chinese-tea encyclopedia writer for an ad-free, authoritative bilingual tea blog. Write clean, structured, SEO-friendly long-form English. Never make medical/cure claims. Tea is a daily beverage, not a substitute for medicine. Never fabricate precise data."},
            {"role": "user", "content": f"Write ONE English article (~800 words) for the '{name}' category.\n"
             + (f"Optional inspiration topic (do not copy verbatim): {topic_hint}\n" if topic_hint else "")
             + f"Use EXACTLY these 9 level-2 headings in order, one per section:\n{head_block}\n\n"
             f"Output format:\n---\ntitle: \"English SEO title\"\nslug: \"english-keywords-slug\"\ndate: \"{date_str}\"\ncategory: \"{cat['id']}\"\ndescription: \"150-160 char summary\"\ncover: \"ancient-tea-tree.jpg\"\n---\n\n"
             f"# Title\n(then the 9 sections above)\n\n"
             f"Naturally mention once: Dazhi brand, rooted in Nahan Village, Jingdong, Yunnan, ecological tea. "
             f"In the Benefits section state clearly: tea is a daily beverage and cannot replace medicine. "
             f"No促销/no hard selling. Output Markdown only."}
        ]
    else:
        return [
            {"role": "system", "content": "你是專業的繁體中文茶文化百科撰稿人。全程繁體，禁止簡體，禁止「哪罕村」（用「哪罕寨」）。客觀、權威、百科式。禁止治病療效宣傳，茶是日常飲品不能替代藥物。不虛構精確數據。"},
            {"role": "user", "content": f"寫一篇繁體中文文章（1000-1200字），欄目：{name}。\n"
             + (f"可選靈感主題（勿照抄）：{topic_hint}\n" if topic_hint else "")
             + f"嚴格按以下 9 個二級標題順序，每段一個：\n{head_block}\n\n"
             f"輸出格式：\n---\ntitle: \"繁體SEO標題\"\nslug: \"english-keywords-slug\"\ndate: \"{date_str}\"\ncategory: \"{cat['id']}\"\ndescription: \"150-160字繁體摘要\"\ncover: \"ancient-tea-tree.jpg\"\n---\n\n"
             f"# 標題\n（然後是上述9段）\n\n"
             f"自然融入一次：大枝品牌扎根雲南景東哪罕寨，生態製茶。{BRAND_CN}\n"
             f"功效段明確寫「茶是日常飲品，不能替代藥物或治療」。不硬廣促銷。只輸出 Markdown。"}
        ]


def normalize(content, lang):
    content = re.sub(r"^```(?:markdown)?\s*\n?", "", content.strip())
    content = re.sub(r"\n?```\s*$", "", content.strip())
    if lang == "zh": content = S2T.convert(content)
    # 強制 9 標題（若模型漏寫，補上）（此處僅做基本清水，完整校驗交 validate.py）
    content = re.sub(r"^(好的|以下是).*?[:：]\s*\n", "", content)
    return content.strip() + "\n"


def main():
    log("INFO", "===== 每日雙語百科文章開始 =====")
    cat, hint = pick_topic()
    log("INFO", f"欄目：{cat['zh']} | 靈感：{hint or '(無)'}")
    date_str = datetime.date.today().isoformat()
    results = {}
    for lang in ["en", "zh"]:
        prompt = build_prompt(cat, hint, lang, date_str)
        content, model = call_llm(prompt)
        if not content:
            log("ERROR", f"{lang} 生成失敗（{model}）→ 中止，避免單語殘缺。")
            return 2
        # 用 slug 統一：以英文版 slug 為準
        if lang == "en":
            sm = re.search(r"^slug:\s*(\S+)", content, re.M)
            slug = sm.group(1).strip('"\'') if sm else f"tea-{datetime.date.today().strftime('%Y%m%d')}"
            results["slug"] = re.sub(r"[^a-z0-9-]", "", slug.lower()) or "tea-post"
        content = normalize(content, lang)
        # 統一 slug 與 cover（兩語一致）
        content = re.sub(r"^slug:.*$", f'slug: "{results["slug"]}"', content, flags=re.M)
        d = os.path.join(ROOT, "content", lang)
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, results["slug"] + ".md")
        open(out, "w", encoding="utf-8").write(content)
        log("INFO", f"{lang} 文章已存 {out}（{model}）")
    log("INFO", "===== 完成 =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
