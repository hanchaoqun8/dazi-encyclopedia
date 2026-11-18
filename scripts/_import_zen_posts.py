# -*- coding: utf-8 -*-
"""一次性导入：哪罕寨 5 篇繁体禅茶文章 → dazi-encyclopedia/content/zh（journal 栏目）。
保留原文正文，只规范化 front matter：栏目、封面路径、SEO 描述、固定 ALT、系列标记。
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = r"F:/Sites/nahan-tea-blog/published"
DST = os.path.join(ROOT, "content", "zh")

META = {
    "morning-mist-original-tea": (
        "哪罕寨地處雲南景東大街鄉哀牢山深處，晨霧繚繞的古茶園裡，原生古茶樹與雲海相伴。"
        "身為世代茶農，我們不炒作山頭、不炒價、不玩金融囤茶，只做老百姓喝得起的平價普洱。"
        "本文從產地風土、做茶本心、禪茶一味與日常飲茶四個角度，記錄一片茶園的質樸與一位茶農的本心。"
    ),
    "fresh-leaf-to-dry-tea": (
        "從枝頭鮮葉到杯中乾茶，中間藏著茶農最質樸的功夫。在雲南景東大街鄉哀牢山深處的哪罕寨，"
        "我們世代自採自製，不假手他人，也不添加花巧。本文順著照片能佐證的環節——採摘、攤晾、乾燥，"
        "如實記錄一份鮮葉如何安靜地變成老百姓喝得起的平價普洱。"
    ),
    "tea-flower-bee-ecology": (
        "茶花開了，蜜蜂便來了。在雲南景東大街鄉哀牢山深處的哪罕寨，茶園不只是採葉的地方，"
        "也是無數小生命安家的所在。花開、蜂來、鳥築巢、葉承露，一切自有秩序。"
        "本文以茶花、蜜蜂、鳥巢與露珠為線，記錄一片雲南原生茶園的小生態，以及不炒作山頭茶、回歸本心的質樸日常。"
    ),
    "zen-tea-simple-cup": (
        "在雲南景東大街鄉哀牢山深處的哪罕寨，茶農的一天從一杯清茶開始。"
        "我們做雲南原生茶，不追名、不逐利、不攀比，只信禪茶一味、喝茶悟道。"
        "勤修戒定慧，遠離貪嗔癡，把修行放進日常。一杯茶湯沉澱浮躁，也照見本心——"
        "做老百姓喝得起、喝得安心的平價普洱，便是我們最樸素的初心。"
    ),
    "four-seasons-pest-observation": (
        "哪罕寨在雲南景東大街鄉哀牢山深處，四季流轉，茶園自有節奏。"
        "我們是世代茶農，做雲南原生茶，不炒作山頭、不炒價。這篇不講玄虛，只記田間實話："
        "椿象、彩虹、紅芽，都是茶園裡常見的小客人。順應自然、不打擾，把茶交給時間——"
        "這便是做百姓良心茶的樸素本分。"
    ),
}
ALT = "哪罕寨原生茶園實拍，雲南景東大街鄉哀牢山"


def main():
    os.makedirs(DST, exist_ok=True)
    for slug, desc in META.items():
        src = os.path.join(SRC, slug + ".md")
        txt = open(src, encoding="utf-8").read()
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
        if not m:
            print("SKIP no front matter:", slug); continue
        fm, body = m.group(1), m.group(2)
        fm = re.sub(r"^cover:\s*.*$", "cover: \"" + os.path.basename(re.search(r'^cover:\s*(\S+)', fm, re.M).group(1).strip('"\'')) + "\"", fm, flags=re.M)
        fm = re.sub(r"^description:\s*.*$", 'description: "' + desc + '"', fm, flags=re.M)
        if not re.search(r"^category:", fm, re.M):
            fm += "\ncategory: journal"
        if not re.search(r"^series:", fm, re.M):
            fm += "\nseries: nahang"
        if not re.search(r"^cover_alt:", fm, re.M):
            fm += '\ncover_alt: "' + ALT + '"'
        out = os.path.join(DST, slug + ".md")
        open(out, "w", encoding="utf-8").write("---\n" + fm.strip() + "\n---\n" + body)
        print("IMPORT", slug, "desc_chars=", len(desc))


if __name__ == "__main__":
    main()
