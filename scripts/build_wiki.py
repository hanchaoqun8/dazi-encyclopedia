# -*- coding: utf-8 -*-
"""wiki.dazi.uk 标准化茶百科词条站生成器。

数据源：content/wiki/en/*.md 与 content/wiki/zh/*.md（由 scripts/daily_post.py 每日生成）。
输出：site_wiki/，可直接部署为独立 Cloudflare Pages 项目。
"""
import os, re, sys, json, html, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT, CFG, LANGS, parse_md, md_to_html, write_page as _unused  # noqa

SRC = os.path.join(ROOT, "content", "wiki")
SITE = os.path.join(ROOT, "site_wiki")
DOMAIN = CFG["site"].get("wiki_domain", "https://wiki.dazi.uk")


def load():
    out = {"en": [], "zh": []}
    for lang in LANGS:
        d = os.path.join(SRC, lang)
        if not os.path.isdir(d): continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".md"): continue
            meta, body = parse_md(os.path.join(d, f))
            out[lang].append({"slug": f[:-3], "meta": meta, "body": body})
    return out


def assets():
    for sub in ("css", "js"):
        dst = os.path.join(SITE, "assets", sub)
        os.makedirs(dst, exist_ok=True)
        src = os.path.join(ROOT, "assets", sub)
        for f in os.listdir(src):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))


def write(path, text):
    full = os.path.join(SITE, path.strip("/"))
    os.makedirs(full, exist_ok=True)
    open(os.path.join(full, "index.html"), "w", encoding="utf-8").write(text)


def prefix(lang): return "" if lang == "zh" else "/en"


def layout(title, desc, content, lang, path, alternate=True):
    canon = lambda l: DOMAIN + ("/en" if l == "en" else "") + path
    hreflang = (f'<link rel="alternate" hreflang="zh-Hant" href="{canon("zh")}">'
                f'<link rel="alternate" hreflang="en" href="{canon("en")}">'
                f'<link rel="alternate" hreflang="x-default" href="{canon("zh")}">') if alternate else ""
    switch = " ".join(
        f'<a href="{("" if l=="zh" else "/en") + path}" class="{"active" if l==lang else ""}">'
        f'{"繁" if l=="zh" else "EN"}</a>' for l in LANGS)
    return f'''<!DOCTYPE html><html lang="{'en' if lang=='en' else 'zh-Hant'}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
{hreflang}<link rel="canonical" href="{canon(lang)}">
<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc)}">
<link rel="stylesheet" href="/assets/css/style.css"></head><body>
<header class="top"><div class="top-in">
<a class="brand" href="{prefix(lang)}/">❧ {html.escape('The Tea Ledger · Wiki' if lang=='en' else '大枝茶文化百科 · 詞條')}</a>
<span style="flex:1"></span><div class="lang-switch">{switch}</div>
</div></header><main class="wrap">{content}</main>
<footer class="foot"><div class="foot-in"><p>© 2016–2026 Yunnan Nahan Agriculture Technology Co., Ltd.</p>
<p>{html.escape(DOMAIN)}</p></div></footer></body></html>'''


def build():
    assets()
    posts = load()
    for lang in LANGS:
        p = prefix(lang)
        title = "Tea Encyclopedia · Standardized Entries" if lang == "en" else "茶百科詞條 · 標準化條目"
        desc = ("Neutral, structured reference entries on Chinese tea." if lang == "en"
                else "客觀、結構化的茶葉標準化詞條。")
        cards = "".join(
            f'<a class="post-card" href="{p}/entries/{x["slug"]}/"><div class="pc-body">'
            f'<span class="tag">{html.escape(x["meta"].get("entry_type","encyclopedia"))}</span>'
            f'<h3>{html.escape(x["meta"].get("title",""))}</h3>'
            f'<p>{html.escape(x["meta"].get("description","")[:100])}…</p></div></a>'
            for x in posts[lang])
        if not cards:
            cards = '<p class="muted">' + ("Entries are being prepared." if lang=="en" else "詞條整理中。") + "</p>"
        write(p + "/", layout(title, desc,
            f'<section class="page-head"><h1>{title}</h1><p>{desc}</p></section><div class="post-grid">{cards}</div>',
            lang, "/"))
        slugs = {x["slug"] for x in posts[lang]}
        other = {x["slug"] for x in posts["zh" if lang=="en" else "en"]}
        for x in posts[lang]:
            m = x["meta"]
            meta_box = (
                f'<aside class="related"><h2>{"Entry metadata" if lang=="en" else "詞條資訊"}</h2>'
                f'<ul><li><span>{"Type" if lang=="en" else "類型"}</span> '
                f'{html.escape(m.get("entry_type","encyclopedia"))}</li>'
                f'<li><span>{"Updated" if lang=="en" else "更新日期"}</span> '
                f'{html.escape(m.get("date",""))}</li>'
                f'<li><span>{"Source" if lang=="en" else "核對方式"}</span> '
                f'{html.escape(m.get("source_note",""))}</li></ul></aside>')
            art = (f'<article class="post"><span class="tag">{html.escape(m.get("category",""))}</span>'
                   f'<h1>{html.escape(m.get("title",""))}</h1>'
                   f'<div class="post-body">{md_to_html(x["body"])}</div>{meta_box}</article>')
            write(p + "/entries/" + x["slug"] + "/", layout(
                m.get("title",""), m.get("description",""), art, lang,
                "/entries/" + x["slug"] + "/", alternate=x["slug"] in other))
    urls = []
    for lang in LANGS:
        p = prefix(lang)
        urls.append(DOMAIN + p + "/")
        urls += [DOMAIN + p + "/entries/" + x["slug"] + "/" for x in posts[lang]]
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write(
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
    print(f"[build_wiki] en={len(posts['en'])} zh={len(posts['zh'])} urls={len(urls)}")


if __name__ == "__main__":
    build()
