# -*- coding: utf-8 -*-
"""
scrape_keigancoffee.py

KEIGAN COFFEE ROASTERS(ケイガンコーヒーロースターズ、keigancoffee.com、静岡県富士市蓼原834-16、
静岡県富士市の自家焙煎スペシャルティコーヒー店)の商品情報を取得する。Shopify。

【店舗発見の経緯】
静岡県の再調査の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`(129商品)のうち product_type が「コーヒー豆」の
商品(シングルオリジン・ブレンド・デカフェ)を対象とする。紅茶(TEAPOND)・ステッカー・パッケージカード・
ブラインドコーヒー体験キット・水出しコーヒーバッグ(コールドブリューブレンド)は除外。
バリエーションは「<焙煎度> / <重量>g」(500gは「20%OFF」付きの大容量)の組で、最小重量
(多くは150g、ゲイシャ等の希少ロットは100g)の価格を代表とする。焙煎度はミディアム/シティの選択がある
商品は先頭のバリエーションの焙煎度を採用する。タイトルの【NEW】【10月のシングルオリジン】等の
告知タグは商品名から除く。TYPICA GUIDE 2025のエチオピア グジ シャキッソ(ローストプロファイル ♢/♦︎)は
別ページの別商品として2件収録する。

【アクセスについて】
Shopifyのレート制限(429)に当たった場合は Retry-After に従って待機し再試行する(回避はしない)。
robots.txtは User-agent: * に Allow: / (products.json は許可)。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "KEIGAN COFFEE ROASTERS",
    "url": "https://keigancoffee.com/",
    "platform": "Shopify",
    "address": "静岡県富士市蓼原834-16",
    "prefecture": "静岡県",
    "robots_txt_status": "許可(User-agent: * は Allow: /。識別可能なUser-Agentを使用、429はRetry-Afterに従う)",
    "source_note": "公式 https://keigancoffee.com/ のトップ(OUR STORE)と /products.json を2026-10-26に確認。住所は公式トップのOUR STORE表記と食べログ。updated_at 2026-10-26で更新は非常に新しい。",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://keigancoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
BEAN_TYPE = "コーヒー豆"
EXCLUDE_KEYWORDS = ("キット", "コールドブリュー", "コーヒーバッグ", "ドリップバッグ", "セット")
VARIANT_PATTERN = re.compile(r"^(?P<roast>[^/]+?)\s*/\s*(?P<w>\d+)g(?:（[^）]*）)?$")
ROAST_NAME = re.compile(r"^(ライトロースト|シナモンロースト|ミディアムロースト|ハイロースト|シティロースト|フルシティロースト|フレンチロースト|イタリアンロースト)")


def fetch_products() -> list[dict]:
    for attempt in range(5):
        resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "60")) + 10
            print(f"[info] 429: Retry-Afterに従い{wait}秒待機")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json().get("products", [])
    raise RuntimeError("429が解消しないため取得できませんでした")


def clean_title(title: str) -> str:
    title = re.sub(r"^(?:【[^】]*】\s*)+", "", title)
    return re.sub(r"\s+", " ", title.replace("　", " ")).strip()


def build_record(p: dict) -> dict | None:
    if p.get("product_type") != BEAN_TYPE:
        return None
    raw_title = p["title"]
    if any(kw in raw_title for kw in EXCLUDE_KEYWORDS):
        return None
    name = clean_title(raw_title)

    weighted = []
    for v in p["variants"]:
        m = VARIANT_PATTERN.match(v["title"])
        if m:
            weighted.append((int(m.group("w")), m.group("roast").strip(), v))
    if not weighted:
        return None
    weight = min(w for w, _, _ in weighted)
    at_min = [(r, v) for w, r, v in weighted if w == weight]
    roast_full, variant = at_min[0]
    available = any(v.get("available") for _, v in at_min)
    roast_m = ROAST_NAME.match(roast_full)
    roast_level = roast_m.group(1) if roast_m else None
    roast_hint = None
    if len({r for r, _ in at_min}) > 1:
        roast_hint = "焙煎度は" + "・".join(sorted({ROAST_NAME.match(r).group(1) for r, _ in at_min if ROAST_NAME.match(r)})) + "から選択"

    body = BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", body)
    desc = re.sub(r"^.*?クーポンを適用する場合は\s*こちら\s*の商品ページから\s*", "", desc)[:400] or None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_decaf = "デカフェ" in raw_title or "カフェインレス" in raw_title
    if "ブレンド" in name or "BLEND" in name.upper():
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "デカフェ" if is_decaf else "ストレート"
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, " ".join(p.get("tags") or []))
        if not parsed["origin_country"] and name.startswith("中国"):
            parsed["origin_country"] = "中国"  # coffee_parserの辞書に無い表記
            parsed["origin_source"] = "raw_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(variant["price"])),
        "weight_g": weight,
        "stock_status": "販売中" if available else "完売",
        "out_of_stock": not available,
        "product_url": f"{BASE_URL}/products/{p['handle']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec is not None:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_keigancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_keigancoffee.json に出力しました")


if __name__ == "__main__":
    main()
