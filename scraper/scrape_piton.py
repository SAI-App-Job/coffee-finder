# -*- coding: utf-8 -*-
"""
scrape_piton.py

炭火珈房ピトン(piton.shop-pro.jp、運営はレ・ユニオンコーヒー株式会社、広島県福山市の備長炭焙煎の
自家焙煎珈琲店)の商品情報を取得する。カラーミーショップ(shop-pro.jpドメイン、文字コードEUC-JP)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。直営店は南蔵王本店・曙店・蔵王店など4店舗で11店舗未満。

【住所について】
公式サイト https://www.piton.co.jp/minami_zaou.html で実データ確認済み(2026-10時点): 「炭火珈房
ピトン南蔵王本店 住所 福山市南蔵王町5丁目16-19 TEL/FAX 084-943-5911」。オンラインショップの特商法
の電話番号(084-943-5911)が本店と一致するため、本店住所を採用する。特商法の「住所」は
レ・ユニオンコーヒー株式会社の本社(福山市春日町5丁目2番32号)だが、店舗の所在地ではないため使わない。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ブレンドコーヒー」(12件)・「ストレートコーヒー」(11件)・
「今月のおすすめ」(4件)の焙煎豆を対象とする(25件=ブレンド13・ストレート12。「炭火ブルーマウンテンブレンド」は今月のおすすめ側のみに掲載)。
除外: ドリップパック・リキッド&オレ・ベース・珈琲ギフトの各カテゴリ(ドリップバッグ・飲料・セット)。
「希望の香り」と「炭火コロンビア アラビカ100% カフェインレス」は、メインカテゴリと「今月のおすすめ」に
別商品ID(希望の香り=117701417/63954920、カフェインレス=117701411/93990632)で同一内容が二重登録
されているため、メインカテゴリ側のみ採用(商品名重複の除外)。「炭火グァテマラ アンティグアSHB」と
「プレミアム 炭火グァテマラ アンティグア SHB」は説明・収穫年が異なる別商品として両方採用する。
全商品が100g〜500gのバリエーション(豆/挽き方指定)を持つため、最小の100g・豆の価格(=一覧表示価格)を採用する。

【在庫・価格・焙煎度について】
価格は税込。在庫は一覧の「SOLD OUT」表示で判定する。焙煎度の記載は商品ページにないためNone
(備長炭焙煎。焙煎度は選択式ではない)。産地は「主な生産地」欄、説明は「特 徴」欄から取得する。

【robots.txtについて】
User-agent: *はDisallow: /secure/・/cart/のみ(実データ確認済み、2026-10)。商品ページは許可。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "炭火珈房ピトン",
    "url": "https://piton.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro)",
    "address": "広島県福山市南蔵王町5丁目16-19",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/・/cart/のみDisallow)",
}

BASE_URL = "https://piton.shop-pro.jp"
# メインカテゴリ(ブレンド・ストレート)を先に処理し、重複する「今月のおすすめ」側を後回しにする
CATEGORY_IDS = [("1489881", "ブレンド"), ("1524790", "ストレート"), ("1524840", "今月のおすすめ")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_BLOCK_PATTERN = re.compile(r'<div class="coffee cr">(.*?)(?=<div class="coffee cr">|Coffee Goods guide|$)', re.S)
ITEM_NAME_PATTERN = re.compile(r'<h3><a href="\?pid=(\d+)">(.*?)</a></h3>', re.S)
PRICE_PATTERN = re.compile(r"([\d,]+)円\(税込\)")
DETAIL_PATTERN = re.compile(r"特\s*徴\s+(.*?)\s+主な生産地\s+(.*?)\s+賞\s*味\s*期\s*限")
COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n", re.S)
ORIGIN_OVERRIDES = {
    "トラジャ": "インドネシア",
    "キリマンジャロ": "タンザニア",
    "エメラルドマウンテン": "コロンビア",
    "モカマタリ": "イエメン",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return re.sub(r"<!--.*?-->", "", resp.text, flags=re.S)


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cbid, cat_label in CATEGORY_IDS:
        html_text = fetch_html(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0")
        for block in ITEM_BLOCK_PATTERN.findall(html_text):
            name_m = ITEM_NAME_PATTERN.search(block)
            if not name_m:
                continue
            pid = name_m.group(1)
            if pid in items:
                continue
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block))
            price_m = PRICE_PATTERN.search(unicodedata.normalize("NFKC", text))
            items[pid] = {
                "pid": pid,
                "name": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", name_m.group(2)))).strip(),
                "list_price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "SOLD OUT" in text.upper(),
                "list_category": cat_label,
            }
        time.sleep(0.5)
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    colorme_m = COLORME_PATTERN.search(html_text)
    product = json.loads(colorme_m.group(1)).get("product", {}) if colorme_m else {}

    # 最小重量(100g)・豆のバリエーションの税込価格
    best = None
    for v in product.get("variants", []):
        w_m = re.search(r"(\d+)", unicodedata.normalize("NFKC", v.get("option1_value") or ""))
        if not w_m or "豆" not in (v.get("option2_value") or ""):
            continue
        weight = int(w_m.group(1))
        if best is None or weight < best[0]:
            best = (weight, v.get("option_price_including_tax"), v.get("stock_num"))

    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    text = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body).replace("&nbsp;", " ")))
    text = re.sub(r"\s+", " ", text)
    detail_m = DETAIL_PATTERN.search(text)
    return {
        "weight": best[0] if best else None,
        "price": best[1] if best else None,
        "variant_stock": best[2] if best else None,
        "product_stock": product.get("stock_num"),
        "description": detail_m.group(1).strip() if detail_m else None,
        "origin_note": detail_m.group(2).strip() if detail_m else None,
    }


def build_record(item: dict) -> dict | None:
    name = item["name"]
    detail = fetch_detail(item["pid"])
    if detail["weight"] is None:
        return None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_blend = item["list_category"] == "ブレンド" or "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break
        if not parsed["origin_country"] and detail["origin_note"]:
            parsed = apply_category_hint_fallback(parsed, detail["origin_note"])

    sold_out = item["sold_out"] or detail["product_stock"] == 0 or detail["variant_stock"] == 0
    price = detail["price"] if detail["price"] is not None else item["list_price"]

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "roast_selectable": False,
        "flavor_notes": detail["description"][:400] if detail["description"] else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": detail["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    seen_names = set()
    for item in list_items():
        # 同一商品が別IDで「今月のおすすめ」に二重登録されているため、商品名重複は後発を除外
        if item["name"] in seen_names:
            continue
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if record is not None:
            seen_names.add(item["name"])
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_piton.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_piton.json に出力しました")


if __name__ == "__main__":
    main()
