# -*- coding: utf-8 -*-
"""
scrape_adayinthecoffee.py

A day in the coffee(adayinthecoffee.com、東京都世田谷区池尻2-4-5 HOME/WORK VILLAGE 114 の自家焙煎所)
の商品情報を取得する。Shopify。

【対象商品について】
実データ確認済み(2026-10時点): Shopifyの`/products.json`のうちproduct_typeが「BEANS」の商品
(ストレート・ブレンド・デカフェ)を対象とする。除外:
- タイトルに「【定期便】」を含む商品(サブスク。同じ豆の100g/200g単品が別に並ぶ)
- DRIPBAG(ドリップバッグ・アイスコーヒーバッグ)、TOOLS、講座・Tシャツ・「コーヒーを選べる◯種類のお楽しみ」等
バリエーションは「<重量>g / 豆|挽き」の組で、豆のままの最小重量(100g)の価格を代表とする。
ブレンドの構成国は説明文の「[ブレンドの内容]」から取得する。
焙煎度は商品ページに明記されておらず、「STRONG BLEND」のみ説明文に「深煎り」とあるため深煎りとした
(他は不明のため null)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "A day in the coffee",
    "url": "https://adayinthecoffee.com/",
    "platform": "Shopify",
    "address": "東京都世田谷区池尻2-4-5 HOME/WORK VILLAGE 114",
    "prefecture": "東京都",
    "robots_txt_status": "確認済み(2026-10-20、User-agent: *で/products.jsonは許可)",
    "source_note": "公式 https://adayinthecoffee.com/pages/access (2026-10-20確認)に「旧池尻中学校跡地の施設、HOME/WORK VILLAGEにある自家焙煎所『A day in the coffee』」とあり、"
                   "Shopifyの/products.jsonのproduct_type=BEANSのうち定期便・ドリップバッグ等を除く単品豆を100g(豆のまま)で収録。"
                   "2025-07-18の告知「焙煎室移転のお知らせ」で老朽化による取り壊しのため世田谷公園隣のHOME/WORK VILLAGEへ移転(同年夏後半)とあり、"
                   "特商法表示 https://adayinthecoffee.com/pages/tokushoho の現所在地は〒154-0001 東京都世田谷区池尻2-4-5 ホームワークヴィレッジ114号室。"
                   "ニュース最新は2025-12-26(年末年始)・2025-10-28(価格改定)。商品データは2026-10-25取得の/products.jsonで、価格・在庫はその時点の値。",
    "last_verified_at": "2026-10-20",
}

BASE_URL = "https://adayinthecoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
BEAN_TYPE = "BEANS"
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")


def scrape_all_products() -> list[dict]:
    resp = requests.get(f"{BASE_URL}/products.json?limit=250", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    products = resp.json().get("products", [])

    records = []
    for p in products:
        if p.get("product_type") != BEAN_TYPE:
            continue
        title = re.sub(r"\s+", " ", p["title"]).strip()
        if "定期便" in title or "subscription_products" in (p.get("tags") or []):
            continue

        weighted = []
        for v in p["variants"]:
            vt = v.get("title") or ""
            m = WEIGHT_PATTERN.search(vt)
            if not m or "挽" in vt:
                continue
            weighted.append((int(m.group(1)), v))
        if not weighted:
            continue
        weight, variant = min(weighted, key=lambda x: x[0])
        available = any(v.get("available") for w, v in weighted if w == weight)

        body_soup = BeautifulSoup(p.get("body_html") or "", "html.parser")
        body = re.sub(r"\s+", " ", body_soup.get_text(" ", strip=True))
        desc = body[:400] or None

        tags = p.get("tags") or []
        is_blend = "blend" in tags or "ブレンド" in title or title.upper().endswith("BLEND") or " BLEND" in title.upper()
        parsed = parse_product(title)
        components = []
        farm_note = None
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            m = re.search(r"\[ブレンドの内容[\]］]\s*(.+?)\s*\[特徴", body)
            if m:
                components = [{"origin_country": c} for c in m.group(1).split() if c]
        else:
            detected = detect_country_name(title) or detect_country_name(title.replace("COSTARICA", "COSTA RICA"))
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, title)
            m = re.match(r"^(.+?)\s*\[特徴", body)
            if m:
                farm_note = m.group(1).strip() or None

        processing = parsed["processing_method"]
        if not processing and not is_blend:
            mp = re.search(r"\[精製方法[\]］]\s*(\S+)", body)
            if mp:
                processing = normalize_processing_method(mp.group(1))
        if is_blend:
            processing = None

        roast_level = "深煎り" if "STRONG BLEND" in title.upper() else None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": farm_note,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": components,
            "price": int(float(variant["price"])),
            "weight_g": weight,
            "stock_status": "販売中" if available else "完売",
            "out_of_stock": not available,
            "product_url": f"{BASE_URL}/products/{p['handle']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_adayinthecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_adayinthecoffee.json に出力しました")


if __name__ == "__main__":
    main()
