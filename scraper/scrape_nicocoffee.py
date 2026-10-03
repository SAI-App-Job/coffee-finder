# -*- coding: utf-8 -*-
"""
scrape_nicocoffee.py

nico caffee roaster(ニコカフェ。nicocoffeeroaster.wixsite.com/nico-shop、神奈川県藤沢市
鵠沼石上2-10-15 1F、江ノ電石上駅徒歩3分。注文を受けてから焙煎する珈琲豆専門店、カフェ
ではない)の商品情報を取得する。Wix製サイトの「COFFEE BLENDS」ページ(/menu、同内容の
/menusあり)に、商品名→説明→「円／100g」→「★焙煎度」→「￥価格」の順でテキストが並ぶ。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。

【対象商品について】
実データ確認済み(2026-10時点・サイトマップ最終更新2026-08-11): 15銘柄中14銘柄
(ストレート11・ブレンド3)。kasuminブレンドは価格が「●●●／100g」と非公開のため
除外(価格を創作しない)。商品名末尾の「＜産地＞」は原産国として使い、商品名からは除く。
「（生豆）」は生豆の販売価格・仕入れ状態を指す注記のため説明文から除去する。
代表重量は全商品100g(表示単位)。焙煎度が複数併記(例:「中深・深ロースト」)のものは
roast_hintに保持しroast_levelはNoneとする。
商品はすべて同一ページのため product_url は商品名の「#フラグメント」で一意化する。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "nico caffee roaster",
    "url": "https://nicocoffeeroaster.wixsite.com/nico-shop",
    "platform": "Wix(価格表・店頭/注文フォーム)",
    "address": "神奈川県藤沢市鵠沼石上2-10-15 1F",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://nicocoffeeroaster.wixsite.com/nico-shop/menu"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
PRICE_PATTERN = re.compile(r"([\d,]+)\s*円\s*[／/]\s*100\s*[gｇ]")
NAME_ORIGIN_PATTERN = re.compile(r"^(.*?)\s*[＜<]\s*(.+?)\s*[＞>]\s*$")


def fetch_lines() -> list[str]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.replace("​", "").strip() for ln in soup.get_text("\n", strip=True).split("\n")]
    return [ln for ln in lines if ln]


def split_blocks(lines: list[str]) -> list[list[str]]:
    """「House Blends」見出し以降を、「★焙煎度」行(+直後の「￥価格」行)で終わるブロックに分割する。"""
    start = next(i for i, ln in enumerate(lines) if ln == "House Blends")
    blocks, cur = [], []
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("nico coffee roaster") or ln.startswith("自家焙煎珈琲"):
            break
        cur.append(ln)
        if "★" in ln:
            if i + 1 < len(lines) and lines[i + 1].startswith("￥"):
                i += 1
            blocks.append(cur)
            cur = []
        i += 1
    return blocks


def scrape_all_products() -> list[dict]:
    records = []
    for block in split_blocks(fetch_lines()):
        text = " ".join(block)
        price_m = PRICE_PATTERN.search(text)
        if not price_m:
            print(f"[skip] 価格非公開: {block[0]}")
            continue
        price = int(price_m.group(1).replace(",", ""))

        head = block[0]
        name_m = NAME_ORIGIN_PATTERN.match(head)
        if name_m:
            name, origin_text = name_m.group(1).strip(), name_m.group(2).strip()
        else:
            name, origin_text = head.strip(), None
        # メキシコ等は名称と1行に説明が続くため、先頭行に説明が混ざる場合は＜産地＞で切る
        name = re.sub(r"\s+", " ", name)

        roast_text = re.search(r"★\s*(\S+)", text).group(1)
        multi_roast = "・" in roast_text

        # 説明文: 名称行と価格表記・焙煎度・￥行を除いた本文
        desc_lines = []
        for ln in block[1:]:
            if ln.startswith("￥"):
                continue
            ln = PRICE_PATTERN.sub("", ln)
            ln = re.sub(r"\s*★.*$", "", ln)
            ln = ln.replace("（生豆）", "").strip()
            if ln:
                desc_lines.append(ln)
        desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip() or None

        is_blend = "ブレンド" in name and not origin_text
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            country = detect_country_name(origin_text) if origin_text else None
            if country and not parsed["origin_country"]:
                parsed["origin_country"] = country
                parsed["origin_source"] = "description"
            parsed = apply_category_hint_fallback(parsed, name)

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": None if multi_roast else roast_text,
            "roast_hint": roast_text if multi_roast else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": 100,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 全商品が同一ページのため一意なフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_nicocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nicocoffee.json に出力しました")


if __name__ == "__main__":
    main()
