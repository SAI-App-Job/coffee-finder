# -*- coding: utf-8 -*-
"""
scrape_itocafe.py

京都伊藤コーヒー(ito-cafe.com、京都府京都市北区小山北上総町43-3 中道ビル1F)の商品情報を
取得する。Jimdo(Jimdoショップ機能)。

【robots.txtについて】
実データ確認済み(2026-10時点): `Disallow: /app/`・`/j/`(ただし`/app/module/webproduct/goto/`は
許可)、`Crawl-Delay: 5`。商品ページ(通常の公開URL)のみを取得し、リクエスト間に5秒の
待機を入れる。

【対象商品について】
sitemap.xmlのうち「/コーヒー豆販売/」配下の商品ページ(カテゴリページ以外=バリエーション
セレクトを持つページ)を対象とする。実データ確認済み(2026-10時点): 商品ページ13件のうち
「ドリップバッグ大谷ブレンド詰合せ」(詰合せ・ドリップバッグ)を除く12件(ブレンド7・
スペシャルティ5)が焙煎豆。バリエーションは「200g/500g × 豆のまま/中挽きペーパー用」の
組で、「【送料調整】…」(送料加算用)は除外し、最小重量(200g)の価格を代表とする。
価格は税込。在庫はバリエーションのavailability(1=在庫あり)で判定する。

【見送った項目】
サイドバーのカタログに載る「マンデリン アチェ ディープグリーン(¥500より)」は、商品リンクの
遷移先(/app/module/webproduct/goto/m/...)がトップページのアンカーに解決されるが、
ページ上に商品モジュール(価格・在庫)が存在せず実際には購入できない状態のため取得しない。

【product_urlについて】
各商品は専用のページURLを持つため、そのURLをそのまま使用する。
"""

import html
import json
import re
import time
import unicodedata
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "京都伊藤コーヒー",
    "url": "https://www.ito-cafe.com/",
    "platform": "Jimdo",
    "address": "京都府京都市北区小山北上総町43-3 中道ビル1F",
    "prefecture": "京都府",
    "robots_txt_status": "許可(2026-10確認。/app/・/j/はDisallow、Crawl-Delay: 5)",
}

BASE_URL = "https://www.ito-cafe.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CRAWL_DELAY = 5
SECTION_PREFIX = "/コーヒー豆販売/"
EXCLUDE_KEYWORDS = ("ドリップバッグ", "詰合せ", "詰め合わせ", "セット", "ギフト")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.I)
COARSE_ROASTS = (
    ("中浅煎り", re.compile(r"中浅煎り")),
    ("中深煎り", re.compile(r"中深煎り")),
    ("浅煎り", re.compile(r"浅煎り")),
    ("中煎り", re.compile(r"中煎り")),
    ("深煎り", re.compile(r"深煎り")),
)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    time.sleep(CRAWL_DELAY)
    return resp.text


def product_page_paths() -> list[str]:
    xml = fetch(f"{BASE_URL}/sitemap.xml")
    paths = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        path = urllib.parse.unquote(urllib.parse.urlparse(loc).path)
        if path.startswith(SECTION_PREFIX) and path != SECTION_PREFIX:
            paths.append(path)
    return paths


def coarse_roast(text):
    for label, pat in COARSE_ROASTS:
        m = pat.search(text or "")
        if m:
            return label, m.group(0)
    return None, None


def parse_variants(module) -> list[dict]:
    variants = []
    for o in module.select("option.j-product__variants__item"):
        label = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", o.get_text(" ", strip=True)))
        if "送料" in label:
            continue
        try:
            params = json.loads(html.unescape(o["data-params"]))
        except (KeyError, ValueError):
            continue
        wm = WEIGHT_PATTERN.search(label)
        if not wm:
            continue
        variants.append({
            "label": label,
            "weight": int(wm.group(1)),
            "price": int(params["price"]),
            "available": params.get("availability") == 1,
        })
    return variants


def build_record(path: str, module) -> dict | None:
    name_el = module.select_one("[itemprop=name]")
    name = re.sub(r"\s+", " ", name_el.get_text(" ", strip=True)).strip() if name_el else None
    if not name or any(k in name for k in EXCLUDE_KEYWORDS):
        return None
    variants = parse_variants(module)
    if not variants:
        return None
    min_weight = min(v["weight"] for v in variants)
    rep = [v for v in variants if v["weight"] == min_weight]
    available = any(v["available"] for v in rep)
    price = rep[0]["price"]

    desc_el = module.select_one("div.description")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)).strip() if desc_el else ""

    is_blend = "ブレンド" in name or "ブレンド" in desc[:20] or "原料豆生産国" in desc
    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(name)
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    roast_level, roast_hint = coarse_roast(name)
    if not roast_level:
        # 説明文中の「深煎り豆を」(パッケージ写真の説明)等は商品自体の焙煎度ではないため除外
        roast_level, roast_hint = coarse_roast(re.sub(r"(浅|中|深|中深|中浅)煎り豆", "", desc))
    if not roast_level:
        rl = parse_product(desc)["roast_level"]
        if rl:
            roast_level, roast_hint = rl, rl

    blend_components = []
    gm = re.search(r"原料豆生産国[：:]\s*([^\s]+)", desc)
    if gm and is_blend:
        for part in re.split(r"[・,、]", gm.group(1)):
            c = detect_country_name(part)
            if c:
                blend_components.append({"origin_country": c})

    processing = parsed["processing_method"] or (None if is_blend else detect_processing_method(desc))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": desc[:400] or None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": blend_components,
        "price": price,
        "weight_g": min_weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": BASE_URL + urllib.parse.quote(path),
    }


def scrape_all_products() -> list[dict]:
    records, seen = [], set()
    for path in product_page_paths():
        soup = BeautifulSoup(fetch(BASE_URL + urllib.parse.quote(path)), "html.parser")
        for module in soup.select("div[id^=cc-m-product-]"):
            rec = build_record(path, module)
            if rec and rec["product_url"] not in seen:
                seen.add(rec["product_url"])
                records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_itocafe.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_itocafe.json に出力しました")


if __name__ == "__main__":
    main()
