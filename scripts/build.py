# -*- coding: utf-8 -*-
"""高端茶葉百科雙語站生成器
英文默认(根路径) / 繁中(/zh-hant/)；7大栏目+品牌5子页；微信私域弹窗；SEO hreflang/sitemap/JSON-LD。
零第三方依赖。
"""
import os, re, json, html, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
CONTENT = os.path.join(ROOT, "content")
SITE = os.path.join(ROOT, "site")
DOMAIN = CFG["site"]["domain"]

LANGS = ["en", "zh"]
LANG_LABEL = {"en": "EN", "zh": "繁"}


def prefix(lang):
    return "" if lang == "en" else "/" + lang


def t(site_key, lang):
    return CFG["site"].get(site_key + ("_en" if lang == "en" else "_zh"), "")


def cat_by_id(cid):
    for c in CFG["categories"]:
        if c["id"] == cid:
            return c
    return CFG["categories"][0]


def lang_switch(path, lang):
    """path 为不含语言前缀的路径，如 /posts/xxx/ 或 /"""
    other = "zh" if lang == "en" else "en"
    def href(l):
        return ("" if l == "en" else "/zh") + path
    return f'''<div class="lang-switch">
<a href="{href('en')}" class="{'active' if lang=='en' else ''}">EN</a>
<a href="{href('zh')}" class="{'active' if lang=='zh' else ''}">繁</a></div>'''


def parse_md(path):
    txt = open(path, encoding="utf-8").read()
    meta, body = {}, txt
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
    if m:
        fm, body = m.group(1), m.group(2)
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def inline(s):
    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s


def md_to_html(body):
    out, para = [], []
    def flush():
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>"); para.clear()
    for ln in body.splitlines():
        t2 = ln.strip()
        if not t2: flush(); continue
        if t2.startswith("## "): flush(); out.append("<h2>"+inline(t2[3:])+"</h2>"); continue
        if t2.startswith("### "): flush(); out.append("<h3>"+inline(t2[4:])+"</h3>"); continue
        if t2.startswith("# "): flush(); continue  # H1 由 layout 统一输出
        if t2.startswith("> "): flush(); out.append("<blockquote>"+inline(t2[2:])+"</blockquote>"); continue
        if t2.startswith("- "):
            flush()
            if not out or not out[-1].startswith("<ul>"): out.append("<ul>")
            out.append("<li>"+inline(t2[2:])+"</li>"); continue
        if out and out[-1].startswith("<ul>"): out.append("</ul>")
        para.append(t2)
    flush()
    if out and out[-1].startswith("<ul>"): out.append("</ul>")
    return "\n".join(out)


def qr_modal(lang):
    if lang == "en":
        title, tip, close = "Scan to Connect", "Scan with WeChat to follow our tea mountain notes and wholesale inquiries.", "Close"
    else:
        title, tip, close = "掃碼聯繫", "用微信掃描，關注茶山日常與批發洽詢。", "關閉"
    return f'''<div class="qr-overlay" id="qrOverlay" onclick="closeQR(event)">
<div class="qr-card" onclick="event.stopPropagation()">
<button class="qr-close" onclick="closeQR()">×</button>
<h3>{title}</h3>
<img src="{CFG['brand']['wechat_qr']}" alt="WeChat QR">
<p>{tip}</p>
</div></div>'''


def layout(title, desc, content, lang, path, schema=None, og_image=None):
    other = "zh" if lang == "en" else "en"
    def canon(l): return (DOMAIN + ("" if l=="en" else "/zh") + path)
    hl = f'<link rel="alternate" hreflang="en" href="{canon("en")}"><link rel="alternate" hreflang="zh-Hant" href="{canon("zh")}"><link rel="alternate" hreflang="x-default" href="{canon("en")}">'
    ogimg = f'<meta property="og:image" content="{DOMAIN}{og_image}">' if og_image else ""
    schema_tag = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>' if schema else ""
    nav_items = "".join(f'<a href="{prefix(lang)}/category/{c["id"]}/">{c["en"] if lang=="en" else c["zh"]}</a>' for c in CFG["categories"])
    footer_nav = "".join(f'<a href="{prefix(lang)}/brand/{p["id"]}/">{p["en"] if lang=="en" else p["zh"]}</a>' for p in CFG["brand_pages"])
    brand = CFG["brand"]
    follow = "Follow" if lang=="en" else "關注"
    brandline = f'{brand["company_en"] if lang=="en" else brand["company_zh"]} · {brand["brand_en"] if lang=="en" else brand["brand_zh"]}'
    return f'''<!DOCTYPE html>
<html lang="{'en' if lang=='en' else 'zh-Hant'}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
{hl}<link rel="canonical" href="{canon(lang)}">
<meta property="og:type" content="article"><meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">{ogimg}
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="/assets/css/style.css">{schema_tag}</head><body>
<header class="top"><div class="top-in">
<a class="brand" href="{prefix(lang)}/"><span class="leaf">❧</span> {html.escape(t('name',lang))}</a>
{nav_items}
{lang_switch(path,lang)}
<button class="qr-btn" onclick="openQR()">{follow}</button>
</div></header>
<main class="wrap">{content}</main>
<footer class="foot"><div class="foot-in">
<p class="brandline">{html.escape(brandline)}</p>
<p>{html.escape(t('tagline',lang))}</p>
<p class="flinks">{footer_nav}</p>
<p class="copy">© 2016–2026 {'Yunnan Nahan Agriculture Technology Co., Ltd.' if lang=='en' else '雲南哪罕農業科技有限公司'}</p>
</div></footer>
{qr_modal(lang)}
<script src="/assets/js/main.js"></script></body></html>'''


def ensure_assets():
    adir = os.path.join(SITE, "assets")
    for sub in ("css", "js", "img"):
        os.makedirs(os.path.join(adir, sub), exist_ok=True)
    src = os.path.join(ROOT, "assets")
    for f in os.listdir(os.path.join(src, "css")):
        shutil.copy2(os.path.join(src, "css", f), os.path.join(adir, "css", f))
    for f in os.listdir(os.path.join(src, "js")):
        shutil.copy2(os.path.join(src, "js", f), os.path.join(adir, "js", f))
    idir = os.path.join(src, "img")
    for f in os.listdir(idir):
        shutil.copy2(os.path.join(idir, f), os.path.join(adir, "img", f))
    # 只复制文章实际用到的封面图（精簡站點體積，利於 GitHub 同步/CI）
    covers = set()
    for lang in LANGS:
        cd = os.path.join(CONTENT, lang)
        if os.path.isdir(cd):
            for f in os.listdir(cd):
                if f.endswith(".md"):
                    meta, _ = parse_md(os.path.join(cd, f))
                    c = os.path.basename(meta.get("cover", ""))
                    if c: covers.add(c)
    tea_img = r"F:/Sites/nahan-tea-blog/images-final"
    if os.path.isdir(tea_img):
        for c in covers:
            src = os.path.join(tea_img, c)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(adir, "img", c))


def write_page(path, html_text):
    full = os.path.join(SITE, path.strip("/"))
    if path == "/": full = SITE
    os.makedirs(full, exist_ok=True)
    open(os.path.join(full, "index.html"), "w", encoding="utf-8").write(html_text)


def load_posts():
    posts = {"en": [], "zh": []}
    for lang in LANGS:
        d = os.path.join(CONTENT, lang)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                meta, body = parse_md(os.path.join(d, f))
                posts[lang].append({"slug": f[:-3], "meta": meta, "body": body})
    return posts


def hero(lang):
    if lang == "en":
        return '''<section class="hero"><div class="hero-in">
<div class="eyebrow">A Tea Encyclopedia · Rooted in Nahan Mountain</div>
<h1>Understand tea,<br>one leaf at a time.</h1>
<p>From Jingdong's Ailao mountains — clean, professional, ad-free tea knowledge. Varieties, brewing, culture, and honest guidance for every cup.</p>
<a class="cta" href="/category/varieties/">Explore the Encyclopedia →</a>
</div></section>'''
    return '''<section class="hero"><div class="hero-in">
<div class="eyebrow">茶葉百科 · 植根哪罕茶山</div>
<h1>讀懂一杯茶，<br>從一片葉開始。</h1>
<p>來自景東哀牢山——乾淨、專業、無廣告的茶知識。品種、沖泡、文化與真實選購建議，陪你喝得明白。</p>
<a class="cta" href="/zh/category/varieties/">進入茶葉百科 →</a>
</div></section>'''


def category_grid(lang):
    cards = []
    for c in CFG["categories"]:
        name = c["en"] if lang=="en" else c["zh"]
        sub = c["en_sub"] if lang=="en" else c["zh_sub"]
        cards.append(f'''<a class="cat-card" href="{prefix(lang)}/category/{c['id']}/">
<span class="cat-icon">{ {'leaf':'❧','cup':'◡','balance':'⚖','search':'⌕','scroll':'❞','pot':'◊','mountain':'▲'}.get(c['icon'],'❧') }</span>
<h3>{name}</h3><p>{sub}</p></a>''')
    return '<section class="section"><h2 class="sec-title">' + ('Explore by Topic' if lang=="en" else '按主題探索') + '</h2><div class="cat-grid">' + "".join(cards) + "</div></section>"


def featured(posts, lang):
    items = posts.get(lang, [])[:6]
    if not items: return ""
    cards = []
    for p in items:
        m = p["meta"]
        cover = m.get("cover", "")
        img = f'<img src="/assets/img/{cover}" alt="" loading="lazy">' if cover else ""
        cards.append(f'''<a class="post-card" href="{prefix(lang)}/posts/{p['slug']}/">
{img}<div class="pc-body"><span class="tag">{cat_by_id(m.get('category','varieties')).get('en' if lang=='en' else 'zh')}</span>
<h3>{html.escape(m.get('title',''))}</h3><p>{html.escape(m.get('description','')[:90])}…</p></div></a>''')
    title = "Latest from the Encyclopedia" if lang=="en" else "百科最新文章"
    return f'<section class="section"><h2 class="sec-title">{title}</h2><div class="post-grid">'+"".join(cards)+"</div></section>"


def brand_teaser(lang):
    b = CFG["brand"]
    if lang == "en":
        return f'''<section class="brand-band"><div class="bb-in">
<div class="eyebrow">Behind the Leaves</div>
<h2>Grown in Nahan. Made with conscience.</h2>
<p>Founded in 2016, {b['company_en']} tends its own原生 garden in Nahan Village, Jingdong, Yunnan — ecological cultivation, restrained craft, and honest tea... </p>
<a class="cta ghost" href="/brand/about/">Our Story →</a></div></section>'''
    return f'''<section class="brand-band"><div class="bb-in">
<div class="eyebrow">茶葉背後</div>
<h2>生於哪罕，良心製茶。</h2>
<p>{b['company_zh']}成立於2016年，在雲南景東哪罕寨守著自有茶園——生態種植、克制工藝、真實做茶。</p>
<a class="cta ghost" href="/zh/brand/about/">認識我們 →</a></div></section>'''


BRAND_PAGES = {
 "about": {
  "en": ("# About Us", "<p>Founded on 10 November 2016, Yunnan Nahan Agriculture Technology Co., Ltd. is based in Nahan Village, Dajie Township, Jingdong, Pu'er, Yunnan. We tend our own tea garden and hold full food-compliance production qualifications.</p><p>Our house brand, Dazhi, covers the whole chain — from garden care and fresh-leaf picking to first processing and brand records. To us, good tea is not a packaged story; it comes from clean ecology, steady craft and long-term consistency.</p><p>This site is not a single product page. It is an open tea-culture journal. Through professional, honest and restrained writing, we help more people understand Yunnan tea — and let the ecological tea of the Nahan mountains become known.</p>"),
  "zh": ("# 關於我們", "<p>雲南哪罕農業科技有限公司，成立於2016年11月10日，總部與茶山基地位於雲南省普洱市景東大街鄉哪罕寨。公司擁有自有茶山茶園與食品合規生產經營資質，長期扎根雲南本地茶產業。</p><p>我們創立自有品牌大枝，堅持從茶園管護、鮮葉採摘、初製加工到品牌記錄的完整鏈路。我們理解的好茶，不是包裝出來的故事，而是來自乾淨的生態、穩定的工藝與長期一致的品質。</p><p>本站不是單一產品銷售頁，而是一個面向茶友開放的茶文化博客。我們希望用專業、真實、克制的茶知識內容，幫助更多人看懂雲南茶，也讓哪罕深山的生態茶被更多人認識。</p>")},
 "garden": {
  "en": ("# Our Garden", "<p>Our garden sits in Nahan Village, Dajie Township, Jingdong, Yunnan — a landscape of encircling forest where tea trees grow alongside mountain ecology. We manage the garden ecologically, respecting the natural rhythm of the trees and limiting unnecessary intervention, so the leaf expresses the place it comes from.</p><p>Mist, moderate sun and day–night temperature differences slow growth and build layers of aroma and body. This is the terroir behind every Dazhi tea.</p>"),
  "zh": ("# 我們的茶山", "<p>我們的茶山位於雲南景東大街鄉哪罕寨。這裡有山林環繞的茶園環境，茶樹與山地生態共同生長。我們以生態管護為基礎，尊重茶樹自然生長規律，減少過度人為干預，努力讓茶葉呈現更接近產地本真的風味。</p><p>霧氣滋潤、日照溫和、日夜溫差讓茶葉慢慢積蓄層次豐富的香氣與湯感——這就是每一片大枝茶背後的風土。</p>")},
 "philosophy": {
  "en": ("# Our Philosophy", "<p>Dazhi holds three commitments:</p><ol><li><strong>Traceable origin</strong> — our own garden and first-processing chain, clear and traceable.</li><li><strong>Ecology first</strong> — respecting the forest environment of Nahan and staying on the ecological-tea path.</li><li><strong>Restrained craft</strong> — no artificial ageing, no forced aroma; the leaf's true character is kept.</li></ol><p>Good tea does not need heavy modification. Clean raw material and moderate craft already express the origin.</p>"),
  "zh": ("# 大枝的製茶理念", "<p>大枝品牌堅持三件事：</p><ol><li><strong>源頭可控</strong>：自有茶山與初製鏈路清楚可追溯；</li><li><strong>生態為本</strong>：尊重哪罕寨山林環境，堅持生態茶方向；</li><li><strong>工藝克制</strong>：不過度做舊，不人為修飾香氣，保留茶葉本味。</li></ol><p>好茶不必靠過度修飾，乾淨的原料與適度的工藝，已經能表達產地本身。</p>")},
 "journal": {
  "en": ("# Brand Journal", "<p>Field notes from Nahan: the four seasons of the garden, the picking season, first processing, the people of the mountain, and the quiet everyday rituals of tea. Recorded plainly — no exaggeration, no hype.</p><p>Browse the <a href='/category/journal/'>Our Tea Mountain</a> column for the latest dispatches.</p>"),
  "zh": ("# 品牌紀實", "<p>來自哪罕寨的田間手記：茶園四季、採摘時節、初製過程、茶山人，以及日常的茶事與茶器。真實、樸素、紀實，不誇大、不炒作。</p><p>前往<a href='/zh/category/journal/'>茶山紀實</a>欄目查看最新記錄。</p>")},
 "contact": {
  "en": ("# Contact", "<p>For garden visits, exchange, wholesale and tea-friend conversations, reach us through the channels below. We keep contact details modest so they never interrupt your reading.</p><p><strong>Phone / WeChat:</strong> +86 13888800714<br><strong>Email:</strong> puer2015tea.qq.com<br><strong>Location:</strong> Nahan Village, Dajie Township, Jingdong, Pu'er, Yunnan</p><p><button class='cta' onclick='openQR()'>Scan WeChat QR</button></p>"),
  "zh": ("# 聯繫我們", "<p>茶山參觀、交流、商務諮詢與茶友溝通，歡迎透過以下方式聯繫。我們克制地放置聯繫方式，不影響主博客的閱讀體驗。</p><p><strong>電話 / 微信：</strong>+86 13888800714<br><strong>郵箱：</strong>puer2015tea.qq.com<br><strong>地址：</strong>雲南省普洱市景東大街鄉哪罕寨</p><p><button class='cta' onclick='openQR()'>掃描微信二維碼</button></p>")}
}


def build():
    ensure_assets()
    posts = load_posts()
    for lang in LANGS:
        p = prefix(lang)
        # 首页
        write_page(p + "/", layout(t("name", lang), t("sub", lang),
            hero(lang) + category_grid(lang) + featured(posts, lang) + brand_teaser(lang),
            lang, "/", schema={"@context":"https://schema.org","@type":"WebSite",
              "name": t("name",lang),"url":DOMAIN+p+"/"}))
        # 栏目页
        for c in CFG["categories"]:
            name = c["en"] if lang=="en" else c["zh"]
            sub = c["en_sub"] if lang=="en" else c["zh_sub"]
            items = [x for x in posts.get(lang,[]) if x["meta"].get("category")==c["id"]]
            cards = "".join(f'''<a class="post-card" href="{p}/posts/{x['slug']}/"><div class="pc-body">
<span class="tag">{name}</span><h3>{html.escape(x['meta'].get('title',''))}</h3>
<p>{html.escape(x['meta'].get('description','')[:100])}…</p></div></a>''' for x in items)
            if not cards:
                cards = '<p class="muted">' + ('Articles in this section are being prepared.' if lang=="en" else '本欄目文章整理中。') + '</p>'
            body = f'<section class="page-head"><div class="eyebrow">Category</div><h1>{name}</h1><p>{sub}</p></section><div class="post-grid">{cards}</div>'
            write_page(p + "/category/" + c["id"] + "/", layout(name, sub, body, lang, "/category/"+c["id"]+"/"))
        # 文章页
        for x in posts.get(lang, []):
            m = x["meta"]
            body_html = md_to_html(x["body"])
            cover = m.get("cover", "")
            cover_html = f'<img class="post-cover" src="/assets/img/{cover}" alt="">' if cover else ""
            content = f'<article class="post"><span class="tag">{cat_by_id(m.get("category","varieties")).get("en" if lang=="en" else "zh")}</span><h1>{html.escape(m.get("title",""))}</h1>{cover_html}<div class="post-body">{body_html}</div><div class="post-foot"><button class="cta" onclick="openQR()">{'Follow for more' if lang=="en" else '關注更多茶知識'}</button></div></article>'
            schema = {"@context":"https://schema.org","@type":"Article","headline":m.get("title",""),
                      "datePublished":m.get("date",""),"description":m.get("description",""),
                      "publisher":{"@type":"Organization","name":CFG["brand"]["company_en"] if lang=="en" else CFG["brand"]["company_zh"]}}
            write_page(p + "/posts/" + x["slug"] + "/", layout(m.get("title",""), m.get("description",""),
                content, lang, "/posts/"+x["slug"]+"/", schema=schema, og_image=("/assets/img/"+cover) if cover else None))
        # 品牌页
        for bp in CFG["brand_pages"]:
            title, body = BRAND_PAGES[bp["id"]][lang]
            write_page(p + "/brand/" + bp["id"] + "/", layout(title.replace("# ",""), t("tagline",lang),
                f'<article class="post page-post">{body}</article>', lang, "/brand/"+bp["id"]+"/"))
    # sitemap
    urls = []
    for lang in LANGS:
        p = prefix(lang)
        urls.append(DOMAIN + p + "/")
        for c in CFG["categories"]: urls.append(DOMAIN + p + "/category/" + c["id"] + "/")
        for bp in CFG["brand_pages"]: urls.append(DOMAIN + p + "/brand/" + bp["id"] + "/")
        for x in posts.get(lang, []): urls.append(DOMAIN + p + "/posts/" + x["slug"] + "/")
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    open(os.path.join(SITE, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\nSitemap: " + DOMAIN + "/sitemap.xml\n")
    print(f"[build] en posts={len(posts['en'])} zh posts={len(posts['zh'])} | urls={len(urls)}")


if __name__ == "__main__":
    build()
