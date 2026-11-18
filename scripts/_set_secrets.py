# -*- coding: utf-8 -*-
"""透過 GitHub API 寫入 Actions Secrets（repo scope 可寫）。

安全約定：本腳本不內嵌任何密鑰。請在環境變數中提供：
  GH_TOKEN, ZHIPU_API_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
可選：REPO（默認 hanchaoqun8/dazi-encyclopedia）
"""
import os, json, base64, urllib.request, urllib.error
from nacl.public import PublicKey, SealedBox

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = os.environ.get("REPO", "hanchaoqun8/dazi-encyclopedia")
BASE = f"https://api.github.com/repos/{REPO}"


def api(path, method="GET", data=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(data).encode() if data else None,
        headers={"Authorization": "Bearer " + TOKEN, "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


NAMES = ["ZHIPU_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
missing = [n for n in NAMES if not os.environ.get(n)]
if not TOKEN or missing:
    raise SystemExit("缺少環境變數：GH_TOKEN, " + ", ".join(missing))

code, key = api("/actions/secrets/public-key")
if code != 200:
    raise SystemExit(f"讀取 public-key 失敗：HTTP {code} {key}")
pub = PublicKey(base64.b64decode(key["key"]))
box = SealedBox(pub)

for name in NAMES:
    value = os.environ[name]
    data = {"encrypted_value": base64.b64encode(box.encrypt(value.encode())).decode(),
            "key_id": key["key_id"]}
    code, res = api(f"/actions/secrets/{name}", method="PUT", data=data)
    print(f"{name}: HTTP {code} ({'OK' if code in (201, 204) else res.get('message')})")

_, lst = api("/actions/secrets")
print("secrets now:", [s["name"] for s in lst.get("secrets", [])])
