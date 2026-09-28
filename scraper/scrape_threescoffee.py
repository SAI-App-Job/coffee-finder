# -*- coding: utf-8 -*-
"""
scrape_threescoffee.py

スリーズコーヒー(Three's Coffee、threes-coffee.com、宮城県仙台市若林区
五橋三丁目5-44 米沢ビル1F、自家焙煎豆のオンライン販売)の商品情報を
取得する。独自EC(Estore製、MakeShop類似のSHOP/コード.html形式URL)。

【店舗発見の経緯】
全国再調査(宮城県)で発見(kitsune-coffee.com「仙台のおすすめコーヒー豆
専門店18選」)。高速焙煎機による焙煎後24-100時間以内の発送を売りにする
専門店。

【対象商品について】
実データ確認済み(2026-09時点): 「ストレートコーヒー」(SHOP/44655/48819)
全19件・「オリジナルブレンド」(SHOP/44655/44656)全9件のうちドリップ
バッグ単品1件を除いた8件、計27件(ストレート19・ブレンド8)を対象とする。
全商品が生豆時量目200gで統一されている。

【エンコーディングについて】
実データ確認済み: サーバーのContent-Typeヘッダーにcharsetが付与されず、
requestsの既定エンコーディング判定がISO-8859-1に外れる(本文のmeta
タグでは"UTF-8"と明記)。resp.encoding="utf-8"の明示が必要。

【商品説明の構造について】
実データ確認済み: `<!-- 商品詳細1 -->`〜`<!-- //商品詳細1 -->`の
HTMLコメントに挟まれた`<p><font>...</font></p>`内に自由記述のテイスティング
文のみが入る(構造化ラベルは無し)。商品名は`<h2 class="title1 no2">`、
価格は`<p class="price no2">`内の`<span>`要素、産地ヒントは`<input
name="IMGALT" value="...">`(ストレート商品では原産国名が入るが、
ブレンド商品では店名が入るため、ストレート商品でのみ産地検出の
補助情報として使う)。商品ページの`<title>`タグは別商品の内容が
キャッシュされたまま表示される実装上の不具合が確認されており(実際の
本文コンテンツとは無関係)、商品名は本文中の`<h2>`から取得する。

【在庫状態について】
実データ確認済み: 一覧ページには「在庫切れ」表示がある商品があるが、
これは商品名やdiv.item-detail-txt1のテキストには一切反映されないため
通常のdetect_stock_status(商品名のみを見る)では検出できない。詳細ページ
本文に`<td class="backcolor2"><p>在庫切れ</p></td>`という構造化
マークアップがあるため、これを検出しstructural_out_of_stockとして
detect_stock_status()に渡す。
"""

import re

import requests

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "スリーズコーヒー",
    "url": "https://www.threes-coffee.com/",
    "platform": "独自EC(Estore)",
    "address": "宮城県仙台市若林区五橋三丁目5-44 米沢ビル1F",
    "prefecture": "宮城県",
    "tel": "022-263-4001",
    "robots_txt_status": "未確認(独自EC構成)",
}

BASE_URL = "https://www.threes-coffee.com"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}

STRAIGHT_CODES = [
    "SS0097", "SS0083", "SS0073", "SS0070", "SS0063", "SS0062", "SS0059",
    "SS0048", "SS0040", "SS0034", "SS0027", "SS0025", "SS0021", "SS0019",
    "SS0014", "SS0012", "SS0008", "SS0005", "SS0001",
]
BLEND_CODES = ["SB0009", "SB0008", "SB0007", "SB0006", "SB0005", "SB0004", "SB0002", "SB0001"]

NAME_PATTERN = re.compile(r'<h2 class="title1 no2">\s*(.+?)\s*</h2>', re.DOTALL)
DESC_PATTERN = re.compile(r"<!-- 商品詳細1 -->(.*?)<!-- //商品詳細1 -->", re.DOTALL)
PRICE_PATTERN = re.compile(r'<p class="price no2"[^>]*>\s*<span[^>]*>([\d,]+)円</span>')
IMGALT_PATTERN = re.compile(r'<input type="hidden" name="IMGALT" value="([^"]*)"')
SOLD_OUT_PATTERN = re.compile(r'<td class="backcolor2"><p>在庫切れ</p></td>')


def build_record(code: str, is_blend: bool) -> dict | None:
    resp = requests.get(f"{BASE_URL}/SHOP/{code}.html", headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    html = resp.text

    name_m = NAME_PATTERN.search(html)
    if not name_m:
        return None
    title = re.sub(r"\s+", " ", name_m.group(1)).strip()

    price_m = PRICE_PATTERN.search(html)
    price = int(price_m.group(1).replace(",", "")) if price_m else None

    desc_m = DESC_PATTERN.search(html)
    flavor_notes = None
    if desc_m:
        text = re.sub(r"<[^>]+>", "\n", desc_m.group(1))
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        flavor_notes = "\n".join(lines) or None

    imgalt_m = IMGALT_PATTERN.search(html)
    origin_hint = imgalt_m.group(1).strip() if (imgalt_m and not is_blend) else None

    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"
    url = f"{BASE_URL}/SHOP/{code}.html"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    if not is_blend:
        detected = (
            (origin_hint and detect_country_name(origin_hint))
            or detect_country_name(title)
            or (flavor_notes and detect_country_name(flavor_notes))
        )
        if detected:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "product_description" if origin_hint else "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)

    structural_out_of_stock = bool(SOLD_OUT_PATTERN.search(html))
    stock_status = detect_stock_status(title, structural_out_of_stock=structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 200,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for code in STRAIGHT_CODES:
        try:
            detail = build_record(code, is_blend=False)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: code={code} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    for code in BLEND_CODES:
        try:
            detail = build_record(code, is_blend=True)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: code={code} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_threescoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_threescoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
