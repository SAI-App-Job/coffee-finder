# -*- coding: utf-8 -*-
"""
scrape_westsidecoffee.py

WESTSIDE COFFEE(westsidecoffee.jp、東京都台東区柳橋2-16-16 ホテルブリリオ浅草橋1F ほか台東区内5拠点、
PROBAT P5で自家焙煎)の商品情報を取得する。Shopify(独自ドメイン)の`/products.json`を使う。

【対象商品について】
実データ確認済み(2026-10-21時点、全28商品): コーヒー豆はproduct_typeが空欄で、器具・Tシャツ・定期便・
コールドブリューバッグ・DIPタイプ(ドリップバッグ)と混在する。バリエーションに「豆のまま」を持つ商品のうち、
定期便・コールドブリュー・DIPを除いたものを対象にする。バリエーション名は「100 / 豆のまま」「60 / ...」
「200 / ...」で重量の単位gが付かない。60gの小分けより100gを優先し、100gが無ければ最小重量。
"""

import json
import re
import time
import urllib.parse

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name,
    detect_stock_status, normalize_processing_method,
)

REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL_SEC = 1.6
WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)(?![a-z])", re.I)
LEADING_NUM_RE = re.compile(r"^\s*(\d+)\s*(?:/|$)")
# 粉・挽き違い(豆のままではない)を示す語。豆のままのバリエーションだけを対象にする
GROUND_WORDS = ("粉", "ドリップ用", "ペーパー", "プレス", "エスプレッソ", "細挽", "中挽", "粗挽")
ROAST_EN = [
    ("full city", "フルシティロースト"), ("light", "ライトロースト"), ("cinnamon", "シナモンロースト"),
    ("medium", "ミディアムロースト"), ("high", "ハイロースト"), ("city", "シティロースト"),
    ("french", "フレンチロースト"), ("italian", "イタリアンロースト"), ("dark", "ダークロースト"),
]


def fetch_products(base: str) -> list[dict]:
    """Shopifyの/products.jsonを全ページ取得する(robots.txtで禁止されていない標準エンドポイント)。"""
    products = []
    page = 1
    while True:
        resp = requests.get(f"{base}/products.json?limit=250&page={page}", headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        batch = resp.json().get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL_SEC)
    return products


def body_text(p: dict) -> str:
    text = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def variant_weight(vtitle: str):
    m = WEIGHT_RE.search(vtitle or "")
    if m:
        w = float(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
        return int(w)
    m = LEADING_NUM_RE.match(vtitle or "")
    if m:
        return int(m.group(1))
    return None


def is_whole_bean_variant(vtitle: str) -> bool:
    return not any(w in (vtitle or "") for w in GROUND_WORDS)


def pick_variant(cands):
    """cands: [(重量g, variant)]。100g以上の最小重量を優先し、無ければ全体の最小重量。"""
    big = [c for c in cands if c[0] >= 100]
    pool = big or cands
    weight = min(c[0] for c in pool)
    same = [c for c in pool if c[0] == weight]
    # 同重量の複数バリエーションは、購入可能なものを代表にする
    same.sort(key=lambda c: (not c[1].get("available"), float(c[1]["price"])))
    return weight, same[0][1]


PROMO_RE = r"(?:NEW|SOLD\s*OUT|終売|完売|残りわずか|大人気|まもなく|オススメ|Special Beans)"


def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title).replace("​", "").replace("⁡", "").strip()
    # 先頭・末尾の販促/状態表記(【NEW!!】【SOLD OUT】【終売】等)は商品名から外す。
    # 【デカフェ】【KURAMAE ORIGINAL BLEND】のような商品の種別を表す括弧は残す
    t = re.sub(rf"^(?:【[^】]*{PROMO_RE}[^】]*】\s*|\[\s*NEW\s*\]\s*)+", "", t, flags=re.I)
    t = re.sub(rf"(?:\s*【[^】]*{PROMO_RE}[^】]*】)+$", "", t, flags=re.I)
    return t.strip()


def roast_from_text(*texts):
    for text in texts:
        if not text:
            continue
        low = text.lower()
        for kw, ja in ROAST_EN:
            if re.search(rf"\b{kw}\s*roast\b", low):
                return ja
    return None


def process_from_body(body: str):
    m = re.search(
        r"(?:Process|精製方法|精製)\s*[:：]\s*(.+?)(?=\s+(?:Flavor|Variety|Altitude|Elevation|Score|Rank|Producer|Farm|Location|品種|収穫|生産者|標高|コメント|焙煎度合|内容量)|\s*$)",
        body,
    )
    if not m:
        return None
    raw = m.group(1).strip()[:60]
    return normalize_processing_method(raw) if raw else None


def build_record(shop_name, base, p, title, weight, variant, origin_override=None, roast=None,
                 desc=None, process=None, blend=False):
    parsed = parse_product(title)
    if blend:
        parsed["category"] = "ブレンド"
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        if origin_override and not parsed["origin_country"]:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "description"
    available = bool(variant.get("available"))
    # 商品名に「終売」「SOLD OUT」等の表記があれば反映し、構造化フラグ(在庫なし)も合わせて判定する
    stock = detect_stock_status(p["title"], structural_out_of_stock=not available)
    return {
        "shop_name": shop_name,
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": process or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"] or roast,
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": weight,
        "stock_status": stock,
        "out_of_stock": stock != "販売中",
        "product_url": f"{base}/products/{urllib.parse.quote(p['handle'])}",
    }


SHOP_INFO = {
    "name": "WESTSIDE COFFEE",
    "url": "https://westsidecoffee.jp/collections/all",
    "platform": "Shopify",
    "address": "東京都台東区柳橋2-16-16 ホテルブリリオ浅草橋1F",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-10-21確認。robots.txtはShopify標準で、/products.jsonは禁止されていない)",
    "source_note": "公式 https://westsidecoffee.jp/pages/shop-info (柳橋・浅草・蔵前ほか台東区内5拠点。柳橋は東京都台東区柳橋2-16-16 1F)、https://westsidecoffee.jp/pages/about (「ROASTING」節:PROBAT P5で豆ごとに焙煎調整、自家焙煎にこだわったコーヒー)、westsidecoffee.jp/products.json(2026-10-21取得、全28商品、最新公開2026-10-08)。ビル名(ホテルブリリオ浅草橋)は特商法ページ由来の調査報告による",
    "last_verified_at": "2026-10-21",
}

BASE_URL = "https://westsidecoffee.jp"
EXCLUDE_TITLE_WORDS = ("定期便", "COLD BREW", "DIP", "セット", "Tee")


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products(BASE_URL):
        title_raw = p["title"]
        if any(w in title_raw for w in EXCLUDE_TITLE_WORDS) or "subscription" in p["handle"]:
            continue
        cands = []
        for v in p["variants"]:
            if "豆のまま" not in (v.get("title") or ""):
                continue
            w = variant_weight(v.get("title"))
            if w is None:
                continue
            cands.append((w, v))
        if not cands:
            continue
        weight, variant = pick_variant(cands)
        body = body_text(p)
        title = clean_title(title_raw)
        # 商品説明の先頭(「【ストーリー」の前)のキャッチ文を説明に使う
        desc = body.split("【ストーリー】")[0].strip()
        if desc.startswith(title):
            desc = desc[len(title):].strip()
        records.append(build_record(
            SHOP_INFO["name"], BASE_URL, p, title, weight, variant,
            roast=roast_from_text(title), desc=(desc[:300] or body[:300] or None),
            process=process_from_body(body),
        ))
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_westsidecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_westsidecoffee.json に出力しました")


if __name__ == "__main__":
    main()
