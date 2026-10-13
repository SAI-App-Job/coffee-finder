# -*- coding: utf-8 -*-
"""
scrape_botchancoffee.py

カフェー工房松山(https://shop.botchancoffee.jp/、愛媛県松山市余戸中3丁目10-33)の商品情報を取得する。カラーミーショップ(EUC-JP)。

【店舗発見の経緯】
全国再調査(愛媛県)で対象とした。ブランド名は「坊っちゃん珈琲」。販売業者は有限会社カフェー工房松山。

【対象商品について】
実データ確認済み(2026-10時点): 全67商品のうち、ドリップバッグ・フレーバー・ギフト・セット・お徳用・紅茶・緑茶・抹茶・インスタント等を除く豆35商品。重量は商品名表記(250g/500g、道後物語等5商品は2袋入りの360g/380g)で、各商品に重量違いの別バリエーションは無く(バリエーションは豆/粉のみ)、その表記重量を代表とした。
対象商品のID・表示名・重量・分類・焙煎度・産地は下のITEMSに明示している。
価格・在庫・説明文は商品ページ(var Colorme のJSONと本文)から取得する。

【在庫について】
var Colorme のstock_numが0以下、または「カートに入れる」ボタンが存在しない商品を品切れとする。

【robots.txtについて】
User-agent: * は /secure/ と /cart/ のみ制限(2026-10確認)。識別可能な独自User-Agentを使用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "カフェー工房松山",
    "url": "https://shop.botchancoffee.jp/",
    "platform": "カラーミーショップ",
    "address": "愛媛県松山市余戸中3丁目10-33",
    "prefecture": "愛媛県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://shop.botchancoffee.jp/"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CRAWL_DELAY_SECONDS = 1

# (商品ID, 表示名, 重量(g), 分類の上書き(Noneなら自動判定), 焙煎度(Noneなら商品名から判定), 産地の上書き(Noneなら自動判定))
ITEMS = [('190618820', '中煎り 自家焙煎コーヒー『道後物語』', 360, 'ブレンド', '中煎り', None),
 ('190527319', '深煎り 自家焙煎コーヒー『深煎り道後物語』', 360, 'ブレンド', '深煎り', None),
 ('188951625', '自家焙煎 カフェインレス ブラジル', 360, None, '中煎り', 'ブラジル'),
 ('178454582', '自家焙煎ストレート珈琲 トロピカルマウンテン', 380, None, '中煎り', 'パプアニューギニア'),
 ('178125017', '自家焙煎 深煎りマンデリンG1', 360, None, '深煎り', 'インドネシア'),
 ('156745897', 'カフェインレス コロンビア', 250, None, None, 'コロンビア'),
 ('54381214', 'モカ イルガチャフェ', 250, None, None, 'エチオピア'),
 ('32536039', 'ブルーマウンテンNo1', 250, None, None, 'ジャマイカ'),
 ('32535878', 'ハワイ・コナ', 250, None, None, 'アメリカ(ハワイ)'),
 ('32534461', 'カロシトラジャ', 250, None, None, 'インドネシア'),
 ('32534265', 'クリスタルマウンテン', 250, None, None, 'キューバ'),
 ('32534113', 'クィーンスマトラ', 250, None, None, 'インドネシア'),
 ('32533726', 'ビルカマウンテン', 250, None, None, 'エクアドル'),
 ('32533606', 'パナマ・バルマウンテン', 250, None, None, 'パナマ'),
 ('32533413', 'コロンビア Qグレード', 250, None, None, 'コロンビア'),
 ('32532717', '陰干珈琲ブラジル・ブルボン Qグレード', 250, None, None, 'ブラジル'),
 ('32532148', 'パプアニューギニアAA', 250, None, None, 'パプアニューギニア'),
 ('32531002', 'ケニアAA Qグレード', 250, None, None, 'ケニア'),
 ('32522246', '無農薬・有機栽培コーヒー', 250, None, None, 'ペルー'),
 ('32522372', 'ブルーマウンテンNo2', 500, None, None, 'ジャマイカ'),
 ('32522178', 'ブルーマウンテンブレンド', 500, 'ブレンド', None, None),
 ('32522130', 'キリマンジャロAA', 500, None, None, 'タンザニア'),
 ('32522017', 'モカ', 500, None, None, 'エチオピア'),
 ('32521950', 'ゴールデンブレンド', 500, 'ブレンド', None, None),
 ('32521892', 'ハイブレンド', 500, 'ブレンド', '中深煎り', None),
 ('32521852', 'アメリカン', 500, 'ブレンド', '浅煎り', None),
 ('32521753', 'マンデリン', 500, None, None, 'インドネシア'),
 ('32521730', 'モカブレンド', 500, 'ブレンド', None, None),
 ('32521691', 'ルビーマウンテン', 500, None, None, 'ベトナム'),
 ('32521602', 'スペシャルブレンド', 500, 'ブレンド', None, None),
 ('32521552', 'マイルド', 500, 'ブレンド', None, None),
 ('32521523', 'アイスコーヒー', 500, 'ブレンド', '極深煎り', None),
 ('32521504', 'ヨーロピアンブレンド', 500, 'ブレンド', None, None),
 ('32521438', 'ブラジル・サントス', 500, None, None, 'ブラジル'),
 ('32470274', 'コロンビア', 500, None, None, 'コロンビア'),
 ('32467228', 'キリマンジャロブレンド', 500, 'ブレンド', None, None)]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)


def fetch_page(pid: str):
    resp = requests.get(f"{BASE_URL}?pid={pid}", headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    soup = BeautifulSoup(resp.text, "html.parser")
    m = COLORME_JSON_PATTERN.search(resp.text)
    product = json.loads(m.group(1)).get("product", {}) if m else {}
    return soup, product


def pick_price(product: dict, weight_g: int) -> int | None:
    pat = re.compile(rf"(?<!\d){weight_g}g")
    for v in product.get("variants", []):
        text = unicodedata.normalize("NFKC", f"{v.get('option1_value') or ''} {v.get('option2_value') or ''}")
        if pat.search(text):
            return v.get("option_price_including_tax")
    return product.get("sales_price_including_tax")


def is_sold_out(soup: BeautifulSoup, product: dict) -> bool:
    stock = product.get("stock_num")
    if isinstance(stock, int) and stock <= 0:
        return True
    return "カートに入れる" not in soup.get_text(" ", strip=True)


def extract_desc_and_roast(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    el = soup.select_one("[class*=expl]")
    text = re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""
    roast_m = re.search(r"■焙煎：\s*(\S+)", text)
    roast = roast_m.group(1) if roast_m else None
    text = re.split(r"この商品は|■原材料名", text)[0].strip()
    return (text[:400] or None), roast



def build_record(item) -> dict | None:
    pid, name, weight_g, category_override, roast_level, origin_override = item
    soup, product = fetch_page(pid)
    desc, page_roast = extract_desc_and_roast(soup)
    sold_out = is_sold_out(soup, product)

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if category_override:
        parsed["category"] = category_override
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if origin_override:
            parsed["origin_country"] = origin_override
            parsed["origin_source"] = "description"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or page_roast or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": pick_price(product, weight_g),
        "weight_g": weight_g,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in ITEMS:
        try:
            record = build_record(item)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item[0]} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(CRAWL_DELAY_SECONDS)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_botchancoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_botchancoffee.json に出力しました")


if __name__ == "__main__":
    main()
