# -*- coding: utf-8 -*-
"""
scrape_kohikoubou.py

珈琲香坊(www.ko-hi-koubou.com、福島県東白川郡矢祭町小田川字中山17-1、定休日 水曜+月最終木曜)の
商品情報を取得する。ショップサーブ(ShopServe、UTF-8)。

【店舗発見の経緯】
全国再調査(福島県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10-12): カテゴリ「１００ｇ単位」(/SHOP/899278/list.html、11件、2ページ)に
自家焙煎のブレンド5銘柄(やまつり・秋空・香坊・つつじヶ丘・八溝山)とストレート6銘柄(タンザニア
ブラックバーン農園・コスタリカ サンタテレサ2000・ガテマラ サンタカタリナ農園・エチオピア
ウォテステーション・ケニア カイナムイファクトリー・ブラジル シーマ農園)が各100gで並ぶ。
同銘柄の200g商品(¥1,800、税込¥1,944)は同一内容の別重量のため収録せず、100g(税込¥1,026)を
代表とする。「ストレート豆６種類セット」「ダンクコーヒーバック」「特選ギフト」「冷んやり珈琲」は
対象外(いずれも100g単位カテゴリに含まれない)。
価格は税込(「税込 ¥1,026」)。在庫は詳細ページの「在庫」欄(「在庫あり」)で判定する。
焙煎度は説明文の「シティーロースト(中煎り)」「フレンチロースト(深煎り)」「浅煎りのブレンド」から取る。
説明は詳細ページの本文(酸味/苦み/香り/コクの★評価を含む)。

【robots.txt】サイトにrobots.txtが無い(404)ことを確認(2026-10-12)。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "珈琲香坊",
    "url": "https://www.ko-hi-koubou.com/",
    "platform": "ショップサーブ",
    "address": "福島県東白川郡矢祭町小田川字中山17-1",
    "prefecture": "福島県",
    "robots_txt_status": "robots.txtなし(404、2026-10確認)",
}

BASE_URL = "https://www.ko-hi-koubou.com"
LIST_URL = f"{BASE_URL}/SHOP/899278/list.html"  # 100g単位カテゴリ
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1
MAX_PAGES = 5
EXCLUDE_KEYWORDS = ("セット", "ギフト", "コーヒーバック", "冷んやり")

ITEM_PATTERN = re.compile(r'<h2><a href="([^"]+)" title="([^"]*)">')
PRICE_TAXIN_PATTERN = re.compile(r"税込\s*(?:&#165;|¥)([\d,]+)")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ー?ロースト")
CATCH_PATTERN = re.compile(r'<p class="inner-catch">(.*?)</p>', re.S)


def fetch(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(3)


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else LIST_URL.replace("list.html", f"list{page}.html")
        html_text = fetch(url)
        new = 0
        for block in html_text.split('<section class="column4">')[1:]:
            m = ITEM_PATTERN.search(block)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            new += 1
            price_m = PRICE_TAXIN_PATTERN.search(block)
            catch_m = CATCH_PATTERN.search(block)
            items.append({
                "path": m.group(1),
                "title": m.group(2),
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "catch": strip_tags(catch_m.group(1)) if catch_m else None,
            })
        if new == 0:
            break
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def fetch_detail(path: str) -> tuple[bool, str | None]:
    """詳細ページから(在庫あり?, 本文)を返す。"""
    html_text = fetch(BASE_URL + path)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    text = unicodedata.normalize("NFKC", strip_tags(text))
    stock_m = re.search(r"在庫\s*(在庫あり|残りわずか|在庫なし|在庫切れ|売り切れ|入荷待ち)", text)
    in_stock = bool(stock_m) and stock_m.group(1) in ("在庫あり", "残りわずか")
    body_m = re.search(r"返品についての詳細はこちら\s*(.*?)\s*(?:この商品を買った人は|-->|$)", text)
    body = re.sub(r"\s*photo by \S+\s*$", "", body_m.group(1)).strip() if body_m else None
    return in_stock, (body[:400] if body else None)


def build_record(item: dict) -> dict | None:
    norm = unicodedata.normalize("NFKC", item["title"])
    if any(kw in norm for kw in EXCLUDE_KEYWORDS):
        return None
    weight_m = WEIGHT_PATTERN.search(norm)
    weight_g = int(weight_m.group(1)) if weight_m else None
    name = re.sub(r"\s*\d+\s*g\s*$", "", norm)
    name = name.replace("のコーヒー豆", "")
    name = re.sub(r"\s+", " ", name).strip()

    in_stock, body = fetch_detail(item["path"])
    desc = body or (unicodedata.normalize("NFKC", item["catch"]) if item["catch"] else None)
    sold_out = not in_stock

    parsed = parse_product(name)
    if parsed["category"] == "ブレンド" or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    catch = unicodedata.normalize("NFKC", item["catch"]) if item["catch"] else ""
    # 焙煎度は一覧のキャッチ(「シティーロースト（中煎り）です」)に書かれ、詳細本文には無い銘柄がある
    roast_m = ROAST_PATTERN.search(catch) or ROAST_PATTERN.search(desc or "")
    roast = (roast_m.group(1) + "ロースト") if roast_m else None
    if not roast:
        blend_roast_m = re.search(r"(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)の(?:ブレンド|コーヒー)", catch + " " + (desc or ""))
        roast = blend_roast_m.group(1) if blend_roast_m else None

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(desc or ""),
        "grade": parsed["grade"],
        "roast_level": roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['path']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kohikoubou.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kohikoubou.json に出力しました")


if __name__ == "__main__":
    main()
