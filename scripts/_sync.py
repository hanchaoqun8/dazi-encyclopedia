# -*- coding: utf-8 -*-
"""增量同步变更文件到 GitHub（Contents API，带 sha 更新）。"""
import os, base64, json, urllib.request, urllib.error, urllib.parse, time

TOKEN = os.environ.get("GH_TOKEN", "")
BASE = "https://api.github.com/repos/hanchaoqun8/dazi-encyclopedia"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".git", "__pycache__", "logs"}


def api(path, method="GET", data=None, retries=3):
    for i in range(retries):
        req = urllib.request.Request(BASE + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req, timeout=40)
            return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())
        except Exception:
            if i < retries-1: time.sleep(2); continue
            return 0, {"message": "retry exhausted"}


_, tree = api("/git/trees/main?recursive=1")
remote = {t["path"]: t["sha"] for t in tree.get("tree", []) if t["type"] == "blob"}

files = []
for root, dirs, fnames in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for fn in fnames:
        if fn.endswith((".pyc", ".log")): continue
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, ROOT).replace("\\", "/")
        files.append((rel, full))

ok = fail = skip = 0
for rel, full in files:
    data = open(full, "rb").read()
    # 若遠端已有相同內容（用 blob sha 比對太麻煩），直接 PUT（帶 sha）
    b64 = base64.b64encode(data).decode()
    payload = {"message": f"sync {rel}", "content": b64, "branch": "main"}
    if rel in remote: payload["sha"] = remote[rel]
    enc = urllib.parse.quote(rel, safe="/")
    code, res = api(f"/contents/{enc}", "PUT", payload)
    if code in (200, 201): ok += 1
    else: fail += 1; print(f"FAIL {rel}: {code} {res.get('message')}")
print(f"[sync] ok={ok} fail={fail} total={len(files)}")
