# -*- coding: utf-8 -*-
"""双语百科文章校验：结构/front matter/繁体/合规/配图。"""
import os, re, sys
from opencc import OpenCC
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S2T = OpenCC("s2t")
IMG = os.path.join(ROOT, "assets", "img")  # 生成器会把配图复制到此处
IMG_FALLBACK = r"F:/Sites/nahan-tea-blog/images-final"
EN_H2 = ["Overview","History & Origin","Craft & Processing","Appearance, Aroma & Taste",
         "How to Brew","Benefits & Who It Suits","Cautions & Considerations",
         "Buying, Authentication & Storage","Final Thoughts"]
ZH_H2 = ["開篇總述","歷史與產地","製作工藝","口感香氣解析","正確沖泡方法",
         "功效與適合人群","禁忌與注意事項","選購鑑別與收藏建議","結語"]
JOURNAL_H2 = ["一、產地真實風土（Wiki科普）","二、茶農做茶本心（核心立場）",
              "三、禪茶一味｜喝茶悟道（修行內核）","四、百姓日常飲茶真義","常見問題（FAQ）"]
BANNED = ["降血壓","減肥","排毒","抗癌","增強免疫力","治癒","療效","神茶","頂級","天花板","稀缺","投資茶","保值茶"]
# 這些詞在否定/免責語境下合法（如「不能替代藥物或治療」「不會因名貴蓋碗而變好」）
CONTEXT_OK = ["不能替代藥物或治療","不会因名贵","不會因名貴","不靠名貴","非名貴",
              "不碰金融茶","金融茶、投資茶","從不碰","不玩金融囤茶"]
# 繁簡同形或 OpenCC 過度轉換的字，跳過不視為簡體
VARIANT_OK = set("峰干欲里后开关克扎群了只才系霉游栗熏床郁准抬并弃台里范托灶核")
CATS = {"varieties","brewing","wellness","buying","culture","teaware","journal"}
SEO_ALT_ZH = "景東大街鄉哪罕那罕古樹茶倉儲數據記錄"
SEO_ALT_EN = "Nahang ancient tea storage data, Dajie Township Jingdong Yunnan"
SEO_KW_ZH = ["景東","大街鄉","哪罕","那罕","Nahang","景東大街鄉普洱茶"]
SEO_KW_EN = ["Jingdong","Dajie Township","Nahang","那罕","Jingdong Dajie Township Pu-erh tea"]


def fm_val(fm, key):
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
    return m.group(1).strip().strip('"\'') if m else ""


def check_seo(fm, body, lang, errs):
    title, desc = fm_val(fm, "title"), fm_val(fm, "description")
    if not (50 <= len(title) <= 60): errs.append(f"SEO title {len(title)} 字符")
    if not (120 <= len(desc) <= 150): errs.append(f"SEO description {len(desc)} 字符")
    want = SEO_ALT_ZH if lang == "zh" else SEO_ALT_EN
    if fm_val(fm, "cover_alt") != want: errs.append("固定 ALT 不符")
    for kw in (SEO_KW_ZH if lang == "zh" else SEO_KW_EN):
        if kw not in fm + body: errs.append(f"缺关键词 {kw}")
    if lang == "zh" and "哪罕（亦作那罕）" not in body: errs.append("缺开篇定位句")
    if lang == "en" and "Nahang (那罕)" not in body: errs.append("缺开篇定位句")


def check(path, lang):
    errs, warns = [], []
    txt = open(path, encoding="utf-8").read()
    fn = os.path.basename(path)
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
    if not m:
        errs.append("缺 front matter"); return errs, warns
    fm, body = m.group(1), m.group(2)
    for k in ["title","slug","date","category","description","cover"]:
        if not re.search(rf"^{k}:", fm, re.M): errs.append(f"缺 {k}")
    cat = re.search(r"^category:\s*(\S+)", fm, re.M)
    if cat and cat.group(1).strip('"\'') not in CATS: errs.append(f"category 无效: {cat.group(1)}")
    if fm_val(fm, "series") == "nahang-data": check_seo(fm, body, lang, errs)
    # 9段式（journal 茶山紀實沿用「四段+FAQ」體例，不強迫改成百科九段）
    heads = re.findall(r"^##\s+(.+)$", body, re.M)
    is_journal = bool(cat and cat.group(1).strip('"\'') == "journal")
    is_zen_zen = is_journal and lang == "zh" and any(h in heads for h in JOURNAL_H2)
    if is_zen_zen:
        for h in JOURNAL_H2:
            if h not in heads: errs.append(f"缺紀實段落 [{h}]")
    else:
        want = EN_H2 if lang=="en" else ZH_H2
        for h in want:
            ok = h in heads
            if not ok and h == "開篇總述": ok = "开篇總述" in heads  # 兼容写法
            if not ok: errs.append(f"缺段落 [{h}]")
    # 字数
    if lang=="zh":
        n = len(re.findall(r"[\u4e00-\u9fff]", body))
        hi = 1800 if is_journal else 1400
        if not (900 <= n <= hi): warns.append(f"中文字数 {n}")
        conv = S2T.convert(txt)
        simp = [f"{a}->{b}" for a,b in zip(txt,conv)
                if a!=b and "\u4e00"<=a<="\u9fff" and "\u4e00"<=b<="\u9fff" and a not in VARIANT_OK]
        if simp: errs.append("简体: "+" ".join(sorted(set(simp))[:15]))
        if "哪罕村" in txt: errs.append("禁用地名 哪罕村")
    else:
        n = len(body.split())
        if not (600 <= n <= 1000): warns.append(f"英文词数 {n}")
    for b in BANNED:
        if b in txt:
            # 若命中詞只出現在免責/否定語境，則合法
            lines = [ln for ln in txt.splitlines() if b in ln]
            if all(any(ok in ln for ok in CONTEXT_OK) for ln in lines):
                continue
            errs.append(f"禁用词 [{b}]")
    # cover 存在（本项目 assets/img 或 茶山图库 fallback）
    cov = re.search(r"^cover:\s*(\S+)", fm, re.M)
    if cov:
        c = os.path.basename(cov.group(1).strip('"').strip("'"))
        if not (os.path.exists(os.path.join(IMG, c)) or os.path.exists(os.path.join(IMG_FALLBACK, c))):
            errs.append(f"cover不存在 {c}")
    warns.insert(0, f"{'字数' if lang=='zh' else '词数'}={n}, 段落={len(heads)}/{'5(紀實)' if is_zen_zen else 9}")
    return errs, warns


def main():
    total = 0
    for lang in ["en","zh"]:
        d = os.path.join(ROOT,"content",lang)
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md"): continue
            errs, warns = check(os.path.join(d,f), lang)
            print(f"\n=== {lang}/{f} ===")
            for w in warns: print("  i", w)
            for e in errs: print("  X", e); total += 1
            if not errs: print("  OK")
    print(f"\n[validate] 错误总数={total}")
    return total

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
