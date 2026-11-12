#!/usr/bin/env python3
"""収集している全店舗の robots.txt を、識別できる User-Agent(CoffeeFinderBot)で確かめて、記録する。

  python -X utf8 scripts/audit_robots.py            # 実行して docs/robots-audit.json・docs/robots-audit.md を作る

見るもの: 商品ページ(data/products.json の product_url。1店舗あたり最大3件)と、店舗のトップページを、CoffeeFinderBot が取得してよいか。
  - allowed       : 許可(robots.txt が無い=404 も、制限なしとして、許可)
  - disallowed    : 禁止(取得してはいけない)
  - unknown       : robots.txt を取得できなかった(接続失敗・5xx・読み取り失敗)。再確認が必要
各ホストに、1回だけアクセスする(間隔をあける。並列は、少数)。利用規約(スクレイピング禁止の条項など)は、ここでは確かめられない。
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
UA = "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"
TOKEN = "CoffeeFinderBot"


def fetch_robots(host_url: str):
    """(状態, robots.txt の本文) 状態: ok / none(404等=制限なし) / error"""
    url = f"{host_url}/robots.txt"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(512 * 1024).decode("utf-8", errors="replace")
            ctype = r.headers.get("Content-Type", "")
            if "html" in ctype.lower() and "user-agent" not in body.lower():
                return "none", ""  # robots.txt の代わりに、HTMLのページが返る(=制限の記載なし)
            return "ok", body
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return "none", ""
        if e.code in (401, 403):
            return "error", f"HTTP {e.code}"
        return "error", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return "error", type(e).__name__


def main():
    products = json.loads((ROOT / "data" / "products.json").read_text(encoding="utf-8"))
    shops = json.loads((ROOT / "data" / "shops.json").read_text(encoding="utf-8"))
    hosts = defaultdict(lambda: {"urls": set(), "shops": set()})
    for p in products:
        u = p.get("product_url") or ""
        pr = urlparse(u)
        if pr.scheme in ("http", "https") and pr.netloc:
            h = hosts[f"{pr.scheme}://{pr.netloc}"]
            if len(h["urls"]) < 3:
                h["urls"].add(u)
            h["shops"].add(p["shop_name"])
    for s in shops:
        pr = urlparse(s.get("url") or "")
        if pr.scheme in ("http", "https") and pr.netloc:
            h = hosts[f"{pr.scheme}://{pr.netloc}"]
            h["urls"].add(s["url"])
            h["shops"].add(s["name"])
    print(f"ホスト {len(hosts)} 件を確認します", flush=True)

    def work(item):
        host, info = item
        time.sleep(0.2)
        state, body = fetch_robots(host)
        result = {"host": host, "shops": sorted(info["shops"]), "state": state, "detail": "", "disallowed": []}
        if state == "error":
            result["verdict"] = "unknown"
            result["detail"] = body
            return result
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        bad = [u for u in sorted(info["urls"]) if not rp.can_fetch(TOKEN, u)]
        result["disallowed"] = bad
        result["verdict"] = "disallowed" if bad else "allowed"
        if state == "none":
            result["detail"] = "robots.txt なし(制限なし)"
        return result

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(work, sorted(hosts.items())))
    counts = defaultdict(int)
    for r in results:
        counts[r["verdict"]] += 1
    out = {"checkedAt": date.today().isoformat(), "userAgent": UA, "counts": dict(counts), "hosts": results}
    (ROOT / "docs" / "robots-audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [
        "# robots.txt の確認記録",
        "",
        f"確認日: {out['checkedAt']} / User-Agent: `{UA}` / 作り方: `python -X utf8 scripts/audit_robots.py`",
        "",
        f"ホスト {len(results)} 件: 許可 {counts['allowed']} / **禁止 {counts['disallowed']}** / 確認できず {counts['unknown']}",
        "",
        "利用規約(スクレイピング禁止の条項など)は、ここでは確かめていない。",
        "",
    ]
    for verdict, title in (("disallowed", "禁止(取得してはいけない)"), ("unknown", "確認できず(再確認が必要)")):
        rows = [r for r in results if r["verdict"] == verdict]
        lines += [f"## {title}: {len(rows)} 件", ""]
        for r in rows:
            lines.append(f"- {r['host']} — {', '.join(r['shops'])}" + (f" — {r['detail']}" if r["detail"] else "") + (f" — 禁止のURL例: {r['disallowed'][0]}" if r["disallowed"] else ""))
        lines.append("")
    (ROOT / "docs" / "robots-audit.md").write_text("\n".join(lines), encoding="utf-8")
    print(dict(counts))


if __name__ == "__main__":
    sys.exit(main())
