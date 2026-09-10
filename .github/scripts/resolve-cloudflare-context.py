import json
import os
import urllib.error
import urllib.request

TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
WORKERS_SUBDOMAIN = "chachasan090375"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() or "{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


status, data = get("https://api.cloudflare.com/client/v4/accounts?per_page=50")
if status != 200 or not data.get("success"):
    raise SystemExit("CLOUDFLARE_ACCOUNTS_FAILED")

accounts = data.get("result") or []
if not accounts:
    raise SystemExit("CLOUDFLARE_ACCOUNT_NOT_FOUND")

chosen = None
for account in accounts:
    account_id = account.get("id")
    status2, project = get(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/pages/projects/wfgg"
    )
    if (
        status2 == 200
        and project.get("success")
        and (project.get("result") or {}).get("name") == "wfgg"
    ):
        chosen = account_id
        break

if not chosen:
    chosen = accounts[0].get("id")
if not chosen:
    raise SystemExit("CLOUDFLARE_ACCOUNT_ID_MISSING")

with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"account_id={chosen}\n")
    output.write(f"subdomain={WORKERS_SUBDOMAIN}\n")

print("CLOUDFLARE_ACCOUNT=OK")
print("WORKERS_SUBDOMAIN=KNOWN_EXISTING")
