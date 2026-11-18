# -*- coding: utf-8 -*-
"""把旧 dazi-tea-blog 的 28 篇欧美执行标准文章迁入双语百科站。
保留原有 5 个子分类（legacy_category），统一归入 standards 栏目。
"""
import os, re, shutil

SRC = r"F:/Sites/dazi-tea-blog/content/posts"
SRC_IMG = r"F:/Sites/dazi-tea-blog/site/assets/img"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DST = os.path.join(ROOT, "content", "en")
DST_IMG = os.path.join(ROOT, "assets", "img")

SUBCATS = {
    "EU Rules": "EU Rules",
    "US Import Rules": "US Import Rules",
    "Testing & Lab Reports": "Testing & Lab Reports",
    "Safety & Storage": "Safety & Storage",
    "Buying Guide": "Buying Guide",
}

os.makedirs(DST, exist_ok=True)
os.makedirs(DST_IMG, exist_ok=True)

moved = []
for fn in sorted(os.listdir(SRC)):
    if not fn.endswith(".md"):
        continue
    txt = open(os.path.join(SRC, fn), encoding="utf-8").read()
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
    if not m:
        print("SKIP no front matter", fn)
        continue
    fm, body = m.group(1), m.group(2)
    cm = re.search(r'^category:\s*"?(.*?)"?\s*$', fm, re.M)
    sub = cm.group(1).strip() if cm else "Buying Guide"
    if sub not in SUBCATS:
        print("SKIP unknown category", fn, sub)
        continue
    # 保留原分类为 legacy_category，主分类改为 standards
    fm2 = re.sub(r'^category:.*$', 'category: "standards"', fm, flags=re.M)
    fm2 += f'\nlegacy_category: "{sub}"\nsource: "dazi-tea-blog legacy archive"\n'
    out = "---\n" + fm2 + "\n---\n" + body
    open(os.path.join(DST, fn), "w", encoding="utf-8").write(out)
    # 封面图
    cov = re.search(r'^cover:\s*"?(.*?)"?\s*$', fm, re.M)
    if cov:
        name = os.path.basename(cov.group(1).strip())
        s = os.path.join(SRC_IMG, name)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(DST_IMG, name))
        else:
            print("MISSING IMG", fn, name)
    moved.append((fn, sub))

print("moved", len(moved))
from collections import Counter
for k, v in Counter(x[1] for x in moved).items():
    print(" ", k, v)
