# -*- coding: utf-8 -*-
"""
scrape_goemon7325.py

7325COFFEE(ナミニココーヒー/五右衛門風呂焙煎所。goemon-7325coffee.com、神奈川県藤沢市
菖蒲沢1129。「HOMEROASTING 7325COFFEE」として自家焙煎した豆を店頭・地方発送で販売)の
商品情報を取得する。Wix製サイトの「地方発送」ページ(/blank-3)に、商品名→焙煎度→
(標高・精選方法等)→価格(税込)→説明の順でテキストが並ぶ。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。

【対象商品について】
実データ確認済み(2026-10時点): 豆8銘柄(ストレート4・ブレンド3・デカフェ1)。
水出しコーヒーパックは豆ではないため除外。ページ末尾の注文方法に「コーヒー豆は100g
単位で袋に入ります」とあり、価格表記(例: 1120円)は100gあたりの税込価格として扱う
(代表重量100g)。ブレンドの使用豆(ケニア・コロンビア等)は説明文に残す。
ページ内に10月の発送日(7・14・21・28日)が掲載されており現行ページ。
商品はすべて同一ページのため product_url は商品名の「#フラグメント」で一意化する。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "7325COFFEE(ナミニココーヒー)",
    "url": "https://www.goemon-7325coffee.com/",
    "platform": "Wix(価格表・メール注文)",
    "address": "神奈川県藤沢市菖蒲沢1129",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://www.goemon-7325coffee.com/blank-3"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_G = 100  # 注文方法欄「コーヒー豆は、100g単位で袋に入ります」
EXCLUDE_KEYWORDS = ("水出し",)
PRICE_PATTERN = re.compile(r"(\d[\d,]*)\s*円")
ROAST_PATTERN = re.compile(r"焙煎度\s*[：:]\s*([^\s]+)")


def fetch_lines() -> list[str]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    lines = [ln.replace("​", "").strip() for ln in soup.get_text("\n", strip=True).split("\n")]
    return [ln for ln in lines if ln]


def parse_blocks(lines: list[str]) -> list[dict]:
    """「焙煎度」行(水出しは「抽出量」行)を各商品ブロックの目印として分割する。"""
    end = next((i for i, ln in enumerate(lines) if ln.startswith("ご注文方法")), len(lines))
    marker_idx = [i for i, ln in enumerate(lines[:end]) if ln.startswith("焙煎度") or ln.startswith("抽出量")]

    blocks = []
    starts = []
    for i in marker_idx:
        # 商品名は目印の直前行。ただしデカフェは「ディカフェ/オーガニック・メキシコ/注記2行」の4行構成
        if lines[i - 1].startswith("（"):
            name = f"{lines[i - 4]} {lines[i - 3]}"
            note = f"{lines[i - 2]}{lines[i - 1]}"
            start = i - 4
        else:
            name, note, start = lines[i - 1], None, i - 1
        starts.append(start)
        blocks.append({"name": name, "note": note, "marker": i})
    for k, b in enumerate(blocks):
        block_end = starts[k + 1] if k + 1 < len(blocks) else end
        b["body"] = lines[b["marker"]:block_end]
    return blocks


def scrape_all_products() -> list[dict]:
    records = []
    for b in parse_blocks(fetch_lines()):
        name = b["name"]
        if any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        body = b["body"]
        roast_m = ROAST_PATTERN.search(body[0])
        roast_text = roast_m.group(1) if roast_m else None
        price = None
        price_idx = None
        for j, ln in enumerate(body):
            if ln.startswith("価格"):
                m = PRICE_PATTERN.search(ln) or (PRICE_PATTERN.search(body[j + 1]) if j + 1 < len(body) else None)
                if m:
                    price = int(m.group(1).replace(",", ""))
                    price_idx = j
                    break
        if price is None:
            continue
        attrs = [ln for ln in body[:price_idx] if not ln.startswith("焙煎度")]
        desc_lines = body[price_idx + 1:]
        desc = " ".join(attrs + desc_lines + ([b["note"]] if b["note"] else []))
        desc = re.sub(r"\s+", " ", desc).strip() or None

        proc_m = re.search(r"精選方法\s*[：:]\s*([^\s]+)", " ".join(attrs))
        parsed = parse_product(name)
        is_blend = "ブレンド" in name
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            detected = detect_country_name(name)
            if detected and not parsed["origin_country"]:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        processing = parsed["processing_method"] or (detect_processing_method(proc_m.group(1)) if proc_m else None)

        is_mix_roast = roast_text and "と" in roast_text  # 「中煎りと深煎りのブレンド」
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": None if is_mix_roast else roast_text,
            "roast_hint": roast_text if is_mix_roast else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": WEIGHT_G,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 全商品が同一ページのため一意なフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_goemon7325.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_goemon7325.json に出力しました")


if __name__ == "__main__":
    main()
