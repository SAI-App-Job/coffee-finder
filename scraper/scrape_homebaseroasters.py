# -*- coding: utf-8 -*-
"""
scrape_homebaseroasters.py

ホームベース焙煎所(homebaseroasters.com、鳥取県東伯郡北栄町由良宿479-1)の商品情報を取得する。Wix Stores。

【取得方法】
実データ確認済み(2026-10): store-products-sitemap.xml の商品ページ(/product-page/<slug>)18件。
各ページのJSON-LD(Product)と埋め込みの productItems / options / additionalInfo(商品情報)を使う。
豆6種(Brazil/Decaf/Ethiopia/Guatemala/Indonesia/Kenya)はそれぞれ商品ページが2つある:
  (A) 「XXX 200g【ｸﾘｯｸﾎﾟｽﾄ便】」 … 200gのみ(2,050〜2,450円)
  (B) 「XXX」(slugが -1 付き) … オプション「内容量: 100g/200g」×「タイプ: 豆のまま/粉」(100gは1,050〜1,250円)
同一銘柄が重量違いで並ぶため、最小重量の100g・豆のまま(B)を代表に採用し、(A)は重複として除外する。
産地・精製方法・焙煎度は「商品情報」欄(生産国/精製方法/品種/焙煎度)から取る。
【除外】HBRオリジナルのTシャツ・グラス・マグカップ(雑貨)、DripBag 5袋セット(ドリップバッグ・セット)。
"""

import json
import re
import time
import unicodedata
from urllib.parse import quote

import requests

from coffee_parser import parse_product, normalize_processing_method

SHOP_INFO = {
    "name": "ホームベース焙煎所",
    "url": "https://www.homebaseroasters.com/",
    "platform": "Wix",
    "address": "鳥取県東伯郡北栄町由良宿479-1",
    "prefecture": "鳥取県",
    "robots_txt_status": "許可(2026-10確認。User-agent: * は Allow: /。商品ページは制限対象外)",
}

SITEMAP_URL = "https://www.homebaseroasters.com/store-products-sitemap.xml"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
NON_BEAN_KEYWORDS = ("Tシャツ", "グラス", "マグカップ", "DripBag", "ドリップ", "セット", "ギフト")
DECAF_PROCESS = "マウンテンウォーター・デカフェ製法(化学的な溶媒を使用しない)"

DEC = json.JSONDecoder()
BIG = 10 ** 9


def fetch(url: str) -> str:
    resp = requests.get(quote(url, safe=":/?=&#%"), headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_product_ld(html: str) -> dict | None:
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def extract_json_after(html: str, key: str):
    k = html.find('"%s":[' % key)
    if k < 0:
        return None
    arr, _ = DEC.raw_decode(html[k + len(key) + 3:])
    return arr


def rich_text(desc_json: str) -> str:
    out = []

    def walk(n):
        if n.get("type") == "TEXT":
            out.append(n["textData"]["text"])
        for c in n.get("nodes", []):
            walk(c)
        if n.get("type") == "PARAGRAPH":
            out.append("\n")

    walk(json.loads(desc_json))
    return "".join(out)


def pick_variant(html: str, title: str):
    """最小重量・豆のままのバリエーションを (重量g, 価格, 在庫あり) で返す。"""
    options = extract_json_after(html, "options") or []
    i = html.find('"productItems":[')
    items = DEC.raw_decode(html[i + len('"productItems":'):])[0] if i >= 0 else []
    weight_opt = next((o for o in options if "内容量" in o.get("title", "")), None)
    type_opt = next((o for o in options if "タイプ" in o.get("title", "")), None)
    sel_w = {}
    if weight_opt:
        for s in weight_opt["selections"]:
            m = re.search(r"(\d+)\s*g", s["value"])
            if m:
                sel_w[s["id"]] = int(m.group(1))
    bean_ids = set()
    if type_opt:
        bean_ids = {s["id"] for s in type_opt["selections"] if "豆" in s["value"] and "粉" not in s["value"]}
    best = None
    for it in items:
        if not it.get("isVisible", True):
            continue
        sels = it.get("optionsSelections") or []
        if type_opt and not (set(sels) & bean_ids):
            continue
        if weight_opt:
            ws = [sel_w[s] for s in sels if s in sel_w]
            w = ws[0] if ws else None
        else:
            m = re.search(r"(\d+)\s*g", title)
            w = int(m.group(1)) if m else None
        cand = (w if w is not None else BIG, it["price"], it.get("inventory", {}).get("status") != "out_of_stock")
        if best is None or cand[:2] < best[:2]:
            best = cand
    if best is None:
        return None
    return (None if best[0] == BIG else best[0], best[1], best[2])


def parse_info(text: str) -> dict:
    d = {}
    for key, label in (("origin", r"生\s*産\s*国"), ("process", r"精製方法"), ("roast", r"焙\s*煎\s*度")):
        m = re.search(label + r"\s*[：:]\s*([^\n]+)", text)
        d[key] = m.group(1).strip() if m else None
    first = text.strip().split("\n")[0].strip()
    d["lead"] = first or None
    return d


def scrape_all_products() -> list[dict]:
    sitemap = fetch(SITEMAP_URL)
    urls = re.findall(r"<loc>([^<]+/product-page/[^<]+)</loc>", sitemap)

    candidates = {}  # 銘柄キー → レコード素材(最小重量を採用)
    for url in urls:
        time.sleep(CRAWL_DELAY_SECONDS)
        html = fetch(url)
        ld = extract_product_ld(html)
        if not ld:
            continue
        title = unicodedata.normalize("NFKC", ld.get("name") or "")
        title = re.sub(r"\s+", " ", title).strip()
        if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
            continue
        var = pick_variant(html, title)
        if var is None:
            continue
        weight, price, available = var
        ai = extract_json_after(html, "additionalInfo") or []
        info = parse_info(rich_text(ai[0]["description"])) if ai else {}
        name = re.sub(r"\s*\d+\s*g\s*【[^】]*】", "", title).strip()
        key = re.split(r"\s*\[", name)[0].strip().lower()
        offer = ld.get("offers") or {}
        if isinstance(offer, list):
            offer = offer[0] if offer else {}
        rec = dict(name=name, weight=weight, price=price, available=available, info=info,
                   url=offer.get("url") or url)
        cur = candidates.get(key)
        if cur is None or (weight or BIG, price) < (cur["weight"] or BIG, cur["price"]):
            candidates[key] = rec

    records = []
    for rec in candidates.values():
        name, info = rec["name"], rec["info"]
        parsed = parse_product(name)
        is_decaf = "decaf" in name.lower()
        if is_decaf:
            parsed["category"] = "デカフェ"
        if info.get("origin"):
            parsed["origin_country"] = info["origin"]
            parsed["origin_source"] = "description"
        proc = info.get("process")
        processing = normalize_processing_method(proc) if proc else parsed["processing_method"]
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": info.get("roast") or parsed["roast_level"],
            "roast_hint": None,
            "flavor_notes": info.get("lead"),
            "farm_note": None,
            "decaf_process": DECAF_PROCESS if is_decaf else None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": rec["price"],
            "weight_g": rec["weight"],
            "stock_status": "販売中" if rec["available"] else "完売",
            "out_of_stock": not rec["available"],
            "product_url": rec["url"],
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_homebaseroasters.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_homebaseroasters.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], r["category"], r["origin_country"], r["processing_method"], r["roast_level"],
              r["price"], r["weight_g"], r["stock_status"], r["product_url"])


if __name__ == "__main__":
    main()
