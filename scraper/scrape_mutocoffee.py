# -*- coding: utf-8 -*-
"""
scrape_mutocoffee.py

MUTO coffee roastery(muto-coffee.com、東京都中野区中野3-34-18。販売業者は株式会社 Lounge M。
自家焙煎の店舗「MUTO coffee roastery」1店舗)の商品情報を取得する。オンラインショップは
EC-CUBE(/shop/)。

【店舗発見の経緯】
全国再調査(東京都)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): オンラインショップのカテゴリ「シングルオリジン」
「オリジナルブレンド」「カフェインレス」(新入荷は重複のため参照のみ)の商品詳細ページ
17商品(ブレンド4・シングル13、デカフェ1含む)を対象とする。ギフトセットカテゴリは除外。
商品名は「コロンビア／ナリーニョ ディエゴ・ロペス 200g」の形式で、すべて200g。
価格は税込表示、焙煎度は商品説明の「焙煎：ハイ/シティ/フレンチ/イタリアン」から取り、
精製は「精製：ウォッシュト」等から取る。在庫は「カートに入れる」ボタンの有無で判定する。

【robots.txtについて】
未確認(EC-CUBE標準構成)。識別可能な独自User-Agentを使用し、リクエスト間隔を空ける。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "MUTO coffee roastery",
    "url": "https://www.muto-coffee.com/shop/",
    "platform": "EC-CUBE",
    "address": "東京都中野区中野3-34-18",
    "prefecture": "東京都",
    "robots_txt_status": "未確認(EC-CUBE標準構成)",
}

BASE_URL = "https://www.muto-coffee.com/shop"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = [1, 2, 7]  # シングルオリジン / オリジナルブレンド / カフェインレス
ROAST_NAMES = {
    "ミディアム": "ミディアムロースト", "ハイ": "ハイロースト", "シティ": "シティロースト",
    "フルシティ": "フルシティロースト", "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}


def get(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    time.sleep(0.8)
    return soup


def list_product_ids() -> list[str]:
    ids: list[str] = []
    for category_id in CATEGORY_IDS:
        for pageno in range(1, 6):
            soup = get(f"{BASE_URL}/products/list?category_id={category_id}&pageno={pageno}")
            found = []
            for a in soup.find_all("a", href=True):
                m = re.search(r"/products/detail/(\d+)", a["href"])
                if m and m.group(1) not in ids and m.group(1) not in found:
                    found.append(m.group(1))
            if not found:
                break
            ids += found
    return ids


def build_record(product_id: str) -> dict | None:
    url = f"{BASE_URL}/products/detail/{product_id}"
    soup = get(url)
    for t in soup(["script", "style"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    start = text.find("Menu ")
    text = text[start + 5:] if start >= 0 else text
    text = text.split("当サイトについて")[0]

    m = re.match(r"(.+?)\s*(\d+)\s*g\s*¥\s*([\d,]+)\s*税込", text)
    if not m:
        return None
    title, weight, price = m.group(1).strip(), int(m.group(2)), int(m.group(3).replace(",", ""))
    name = re.sub(r"\s+", " ", title.replace("／", " ").replace("/", " ")).strip()

    category_m = re.search(r"関連カテゴリ[:：]\s*(.*?)\s*(?:カートに入れる|売り切れ|SOLD)", text)
    category_text = category_m.group(1) if category_m else ""
    in_stock = "カートに入れる" in text
    roast_m = re.search(r"焙煎[:：]\s*(フルシティ|ミディアム|ハイ|シティ|フレンチ|イタリアン)", text)
    roast_level = ROAST_NAMES[roast_m.group(1)] if roast_m else None
    process_m = re.search(r"精製[:：]\s*(\S+)", text)
    processing = detect_processing_method(process_m.group(1).replace("ウオッシュ", "ウォッシュ")) if process_m else None
    desc_m = re.search(r"焙煎[:：]\s*\S+\s*(.*)$", text)
    desc = desc_m.group(1).strip()[:400] if desc_m else None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if "オリジナルブレンド" in category_text or "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing or parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for product_id in list_product_ids():
        try:
            record = build_record(product_id)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: id={product_id} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mutocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mutocoffee.json に出力しました")


if __name__ == "__main__":
    main()
