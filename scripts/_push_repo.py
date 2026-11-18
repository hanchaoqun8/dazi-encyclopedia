# -*- coding: utf-8 -*-
"""用 Git Data API 一次性提交整个项目到 GitHub（避免逐文件 API 限流/断连）。"""
import os, base64, json, urllib.request, urllib.error

TOKEN = os.environ.get("GH_TOKEN", "")
OWNER_REPO = "hanchaoqun8/dazi-encyclopedia"
BASE = f"https://api.github.com/repos/{OWNER_REPO}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", "__pycache__", "logs"}


def api(path, method="GET", data=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


# 确保仓库存在
code, repo = api("")
if code == 404:
    # 创建
    req = urllib.request.Request("https://api.github.com/user/repos", method="POST",
        data=json.dumps({"name": "dazi-encyclopedia",
            "description": "blog.dazi.uk - 大模型驱动的高端双语茶叶百科博客 (EN/繁中)",
            "homepage": "https://blog.dazi.uk", "private": False, "auto_init": False}).encode(),
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=40)
    print("created repo:", json.loads(r.read().decode()).get("full_name"))

# 收集文件
files = []
for root, dirs, fnames in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for fn in fnames:
        if fn.endswith((".pyc", ".log")): continue
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, ROOT).replace("\\", "/")
        files.append((rel, full))
print(f"files to upload: {len(files)}")

# 分批建 blob（每批 50，避免单次过大）
tree_entries = []
for i, (rel, full) in enumerate(files):
    data = open(full, "rb").read()
    code, blob = api("/git/blobs", "POST", {"content": base64.b64encode(data).decode(), "encoding": "base64"})
    if code != 201:
        print(f"blob FAIL {rel}: {code} {blob.get('message')}"); continue
    tree_entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    if (i+1) % 20 == 0: print(f"  blobs {i+1}/{len(files)}")
print(f"blobs created: {len(tree_entries)}")

# 建 tree（空仓库无 base_tree）
code, tree = api("/git/trees", "POST", {"tree": tree_entries})
if code != 201:
    print("TREE FAIL", code, tree.get("message")); raise SystemExit(1)
print("tree:", tree["sha"][:8])

# 建 commit
code, commit = api("/git/commits", "POST", {
    "message": "Initial: bilingual tea encyclopedia (EN/繁中) - 7 categories, 14 articles, brand pages",
    "tree": tree["sha"]})
if code != 201:
    print("COMMIT FAIL", code, commit.get("message")); raise SystemExit(1)
print("commit:", commit["sha"][:8])

# 建 main ref（新仓库）
code, ref = api("/git/refs", "POST", {"ref": "refs/heads/main", "sha": commit["sha"]})
if code == 201:
    print("main branch created")
elif code == 422:
    # 已存在则更新
    api("/git/refs/heads/main", "PATCH", {"sha": commit["sha"], "force": False})
    print("main branch updated")
else:
    print("REF FAIL", code, ref.get("message")); raise SystemExit(1)
print("SUCCESS ->", f"https://github.com/{OWNER_REPO}")
