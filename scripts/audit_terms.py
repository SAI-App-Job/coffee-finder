#!/usr/bin/env python3
"""収集している店舗サイトの、利用規約・サイトポリシーに、自動取得・転載などを禁じる記載がないか、機械的に拾う(要確認の店舗の絞り込み用)。

  python -X utf8 scripts/audit_terms.py              # 全ホスト(docs/robots-audit.json で許可だったもの)
  python -X utf8 scripts/audit_terms.py --limit 30   # 試し(先頭30ホスト)

やること(1ホストあたり、最大 1+3 ページ。識別できる User-Agent。ホストごとに間隔をあけ、少数だけ並列):
  1. トップページから、同じホストの、規約系のリンク(利用規約・サイトポリシー・ご利用案内・著作権・免責 など)を探す。
  2. そのページ(最大3件)の本文から、次を探す。robots.txt で禁止されているページは取得しない。
     - 自動取得系の語(スクレイピング・クローリング・ロボット・自動取得・機械的な収集 など)の近くに、禁止の語(禁止・禁じ・お断り など)があるもの → **要確認(auto)**
     - 「無断転載・複製の禁止」などの定型文 → 参考(reprint)。ほとんどの店舗に有る定型文で、事実情報の掲載を禁じるものではない
  3. 結果を docs/terms-audit.json・docs/terms-audit.md に書く(店舗の文章は、写さない。URL と、見つけた語だけを記録する)。
     文脈の抜粋は、git 管理外の terms-audit-details.json(リポジトリ直下)に書く(人が確認するときの手がかり)。
限界: 規約が画像・PDF・JavaScript で出るサイト、リンクが見つからないサイトは、判定できない(not_found)。これは、機械的な絞り込みで、最終判断は、人が行う。
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
UA = "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"
TOKEN = "CoffeeFinderBot"
MAX_BYTES = 600 * 1024
PAGES_PER_HOST = 3
DELAY = 0.8

LINK_WORDS = re.compile(
    r"(利用規約|ご利用規約|サイトポリシー|サイト利用|サイトのご利用|ご利用にあたって|ご利用上|ご利用案内|ご利用ガイド|利用条件|ご利用条件|著作権|免責|"
    r"terms|term-of|policy|copyright|disclaimer|rule)",
    re.I,
)
LINK_EXCLUDE = re.compile(r"(privacy|プライバシー|個人情報|特定商取引|tokusho|shipping|返品|配送|送料|cookie|クッキー)", re.I)
AUTO = re.compile(
    r"(スクレイピング|スクレーピング|クローリング|クローラ|クロール|ロボット|bot\b|crawler|scrap\w*|"
    r"自動(?:的)?(?:に|で|の)?(?:取得|収集|アクセス|ダウンロード|抽出|巡回)|機械的(?:に|な)?(?:取得|収集|アクセス|複製)|データ(?:の)?(?:収集|抽出|マイニング))",
    re.I,
)
PROHIBIT = re.compile(r"(禁止|禁じ|いけません|してはなりません|お断り|認めて|できません|禁ずる)")
REPRINT = re.compile(r"(無断(?:で)?(?:転載|複製|使用|利用|引用|コピー)|転載|複製|二次利用|再配布)")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type", "")
        data = r.read(MAX_BYTES)
        return data, ctype, r.geturl()


def decode(data, ctype):
    m = re.search(r"charset=([\w-]+)", ctype, re.I)
    enc = m.group(1) if m else None
    if not enc:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", data[:4096], re.I)
        enc = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    for e in (enc, "utf-8", "cp932", "euc-jp"):
        try:
            return data.decode(e)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", "replace")


def to_text(html_body):
    t = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html_body, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return unicodedata.normalize("NFKC", re.sub(r"\s+", " ", unescape(t)))


def find_links(html_body, base):
    host = urlparse(base).netloc
    found = []
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", html_body, flags=re.S | re.I):
        href, label = m.group(1).strip(), re.sub(r"<[^>]+>", "", m.group(2))
        label = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", unescape(label))).strip()
        url = urljoin(base, href)
        pr = urlparse(url)
        if pr.scheme not in ("http", "https") or pr.netloc != host:
            continue
        probe = f"{label} {pr.path}"
        if LINK_WORDS.search(probe) and not LINK_EXCLUDE.search(probe):
            if re.search(r"\.(pdf|jpg|png|zip)$", pr.path, re.I):
                continue
            found.append((0 if re.search(r"(利用規約|terms)", probe, re.I) else 1, url.split("#")[0]))
    out = []
    for _, u in sorted(found):
        if u not in out:
            out.append(u)
    return out[:PAGES_PER_HOST]


WIDE = 300  # 「以下の行為を禁止します」の見出しのあとに、項目が並ぶ形(禁止の語が、離れている)を拾う範囲


def analyze(text):
    """(auto の該当語の一覧, reprint の有無, 抜粋)。禁止の語が近く(前後70字)にあれば強い疑い、少し離れて(前後300字)あれば、弱い疑い(末尾に「*」)"""
    auto_hits, snippets = [], []
    for m in AUTO.finditer(text):
        near = text[max(0, m.start() - 70): m.end() + 70]
        wide = text[max(0, m.start() - WIDE): m.end() + WIDE]
        if PROHIBIT.search(near):
            auto_hits.append(m.group(0))
            snippets.append(near)
        elif PROHIBIT.search(wide):
            auto_hits.append(m.group(0) + "*")
            snippets.append(wide[:200])
    rep = any(PROHIBIT.search(text[max(0, m.start() - 40): m.end() + 40]) for m in REPRINT.finditer(text))
    return sorted(set(auto_hits)), rep, snippets[:3]


def check_host(item):
    host_url, info = item
    res = {"host": host_url, "shops": info["shops"], "status": "", "pages": [], "auto": [], "reprint": False}
    snippets = []
    try:
        rp = urllib.robotparser.RobotFileParser()
        try:
            body, _, _ = fetch(f"{host_url}/robots.txt")
            rp.parse(body.decode("utf-8", "replace").splitlines())
        except Exception:  # noqa: BLE001
            rp = None
        time.sleep(DELAY)
        data, ctype, final = fetch(host_url + "/")
        html_body = decode(data, ctype)
        links = find_links(html_body, final)
        if not links:
            res["status"] = "not_found"
            return res, snippets
        for u in links:
            if rp is not None and not rp.can_fetch(TOKEN, u):
                continue
            time.sleep(DELAY)
            try:
                d, c, f = fetch(u)
            except Exception:  # noqa: BLE001
                continue
            if "pdf" in c.lower() or "html" not in c.lower() and "text" not in c.lower():
                continue
            auto, rep, snip = analyze(to_text(decode(d, c)))
            res["pages"].append(f)
            res["auto"] = sorted(set(res["auto"]) | set(auto))
            res["reprint"] = res["reprint"] or rep
            snippets += [{"url": f, "text": s} for s in snip]
        if not res["pages"]:
            res["status"] = "not_found"
        else:
            res["status"] = "auto" if res["auto"] else ("reprint" if res["reprint"] else "ok")
    except Exception as e:  # noqa: BLE001
        res["status"] = "error"
        res["error"] = type(e).__name__
    return res, snippets


def recheck(path):
    """前回の結果(terms-audit.json)で、規約のページが見つかったホストについて、そのページだけを、取得し直して判定し直す(判定の条件を変えたとき用)"""
    prev = json.loads(Path(path).read_text(encoding="utf-8"))
    results, details = [], {}
    targets = [h for h in prev["hosts"] if h.get("pages")]
    print(f"規約のページが見つかった {len(targets)} ホストを、判定し直します", flush=True)

    def work(h):
        res = {**h, "auto": [], "reprint": False}
        snips = []
        for u in h["pages"]:
            time.sleep(DELAY)
            try:
                d, c, f = fetch(u)
            except Exception:  # noqa: BLE001
                continue
            auto, rep, snip = analyze(to_text(decode(d, c)))
            res["auto"] = sorted(set(res["auto"]) | set(auto))
            res["reprint"] = res["reprint"] or rep
            snips += [{"url": f, "text": x} for x in snip]
        res["status"] = "auto" if res["auto"] else ("reprint" if res["reprint"] else "ok")
        return res, snips

    with ThreadPoolExecutor(max_workers=6) as ex:
        for res, snips in ex.map(work, targets):
            results.append(res)
            if snips:
                details[res["host"]] = snips
    by = {r["host"]: r for r in results}
    prev["hosts"] = [by.get(h["host"], h) for h in prev["hosts"]]
    counts = defaultdict(int)
    for h in prev["hosts"]:
        counts[h["status"]] += 1
    prev["counts"] = dict(counts)
    Path(path).write_text(json.dumps(prev, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ROOT / "terms-audit-details.json").write_text(json.dumps(details, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(dict(counts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recheck", action="store_true", help="前回の結果で規約が見つかったホストだけ、判定し直す")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.recheck:
        recheck(ROOT / "docs" / "terms-audit.json")
        return
    robots = json.loads((ROOT / "docs" / "robots-audit.json").read_text(encoding="utf-8"))
    hosts = [(h["host"], {"shops": h["shops"]}) for h in robots["hosts"] if h["verdict"] == "allowed"]
    if a.limit:
        hosts = hosts[: a.limit]
    print(f"ホスト {len(hosts)} 件を確認します", flush=True)
    results, details = [], {}
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for res, snips in ex.map(check_host, hosts):
            results.append(res)
            if snips:
                details[res["host"]] = snips
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(hosts)}", flush=True)
    counts = defaultdict(int)
    for r in results:
        counts[r["status"]] += 1
    out = {"checkedAt": date.today().isoformat(), "userAgent": UA, "counts": dict(counts), "hosts": results}
    if not a.limit:
        (ROOT / "docs" / "terms-audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (ROOT / "terms-audit-details.json").write_text(json.dumps(details, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        lines = [
            "# 店舗サイトの規約の、機械的な確認",
            "",
            f"確認日: {out['checkedAt']} / 作り方: `python -X utf8 scripts/audit_terms.py`",
            "",
            f"ホスト {len(results)} 件: 要確認(自動取得を禁じる記載の疑い) {counts['auto']} / 定型の転載禁止のみ {counts['reprint']} / 記載なし {counts['ok']} / 規約のページが見つからず {counts['not_found']} / 取得できず {counts['error']}",
            "",
            "これは機械的な絞り込みで、最終判断は人が行う。「要確認」は、規約のページ(下記URL)を開いて、実際の文言を確かめる。店舗の文章は、ここには写していない。",
            "",
            f"## 要確認(auto): {counts['auto']} 件",
            "",
        ]
        for r in results:
            if r["status"] == "auto":
                lines.append(f"- {', '.join(r['shops'])} — {r['host']} — 語: {', '.join(r['auto'])} — {' / '.join(r['pages'])}")
        (ROOT / "docs" / "terms-audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(dict(counts))


if __name__ == "__main__":
    sys.exit(main())
