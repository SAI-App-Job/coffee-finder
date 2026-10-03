# -*- coding: utf-8 -*-
"""
scrape_pengincoffee.py

ペンギン珈琲(p-mame.com、神奈川県川崎市麻生区千代ケ丘7-4-15。地域密着型の自家焙煎
コーヒー豆店。店舗は1店、小田急線新百合ケ丘駅からバス)の商品情報を取得する。
静的ページ「Order」(order.html)に、「ストレートコーヒー豆」「限定豆」「ブレンドコーヒー豆」
「おとく豆」の各表があり、商品コード(S-01等)→商品名→焙煎度合→200g・100gの税込価格→
説明の順で並ぶ。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。ページ冒頭に「10月のコーヒー」があり、店舗情報のカレンダー
が2026年10月・11月で現行。所在地はShop(ShopInfo.html)ページの「川崎市麻生区千代ケ丘 7-4-15」。

【対象商品について】
実データ確認済み(2026-10時点): ストレート7・限定豆1(今月のコーヒー)・ブレンド2・
おとく豆1(スタンダードグレードのブラジル、200g単位のみ)の計11銘柄。
ドリップバッグ(5pc/21pc)・ギフトセットは除外。代表重量は表示された最小サイズ
(100gの表があるものは100g、おとく豆は200gのみ)。「今月のコーヒー」の見出し部の
「200g/2,180→2,150」は期間割引表記のため使わず、表内の通常価格を用いる。
焙煎度が範囲表記(例:「中〜中深煎」)のものは roast_hint に保持し roast_level はNone。
商品はすべて同一ページのため product_url は商品名の「#フラグメント」で一意化する。
"""

import json
import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ペンギン珈琲",
    "url": "https://www.p-mame.com/",
    "platform": "静的HTML(Bindsite・メール注文)",
    "address": "神奈川県川崎市麻生区千代ケ丘7-4-15",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

PAGE_URL = "https://www.p-mame.com/order.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

SECTIONS = ("ストレートコーヒー豆", "限定豆", "ブレンドコーヒー豆", "おとく豆")
CODE_PATTERN = re.compile(r"^[A-Z]{1,3}-\d+$")
ROAST_PATTERN = re.compile(r"^[^\s¥]{1,14}煎$")
WEIGHT_PATTERN = re.compile(r"^(\d+)g$")


def fetch_lines() -> list[str]:
    resp = requests.get(PAGE_URL, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]


def scrape_all_products() -> list[dict]:
    lines = fetch_lines()
    records = []
    section = None
    weights: list[int] = []  # 現在の表の列(例: [200, 100])
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln in SECTIONS:
            section = ln
            weights = []
            # 見出し直後の「焙煎度合」「200g」「100g」から列(重量)を取る
            j = i + 1
            while j < len(lines) and not CODE_PATTERN.match(lines[j]):
                wm = WEIGHT_PATTERN.match(lines[j])
                if wm:
                    weights.append(int(wm.group(1)))
                j += 1
            i += 1
            continue
        if not CODE_PATTERN.match(ln) or section is None:
            i += 1
            continue

        # 商品ブロック: コード → [New!] → 商品名(1〜2行) → 焙煎度合 → (¥ 価格)×n → 説明
        j = i + 1
        name_lines = []
        while j < len(lines) and not ROAST_PATTERN.match(lines[j]):
            if lines[j] != "New!":
                name_lines.append(lines[j])
            j += 1
            if j - i > 6:
                break
        if j >= len(lines) or not ROAST_PATTERN.match(lines[j]):
            i += 1
            continue
        roast_text = lines[j]
        j += 1
        prices = []
        while j + 1 < len(lines) and lines[j] == "¥" and re.fullmatch(r"[\d,]+", lines[j + 1]):
            prices.append(int(lines[j + 1].replace(",", "")))
            j += 2
        desc_lines = []
        while j < len(lines) and not CODE_PATTERN.match(lines[j]) and lines[j] not in SECTIONS:
            if lines[j].startswith(("ドリップバッグ", "5pc", "21pc", "ギフトを承ります")):
                break
            desc_lines.append(lines[j])
            j += 1
        i = j

        if not prices or not name_lines:
            continue
        if name_lines[0] == "今月のコーヒー" and len(name_lines) > 1:
            name_lines = name_lines[1:]
        name = re.sub(r"\s+", " ", " ".join(name_lines).replace("　", " ")).strip()
        # 列数と価格数が一致する場合のみ列(重量)に対応づける。ずれる場合は最小列を末尾の価格とする
        pairs = list(zip(weights, prices)) if len(weights) == len(prices) else []
        if pairs:
            weight_g, price = min(pairs)
        else:
            weight_g, price = None, prices[-1]
        desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip() or None

        is_blend = section == "ブレンドコーヒー豆" or "ブレンド" in name
        parsed = parse_product(name)
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

        ranged = "〜" in roast_text or "~" in roast_text or "～" in roast_text
        if section == "限定豆":
            desc = f"今月のコーヒー。{desc}" if desc else "今月のコーヒー"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": None if ranged else roast_text,
            "roast_hint": roast_text if ranged else None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight_g,
            "stock_status": "販売中",
            "out_of_stock": False,
            "product_url": f"{PAGE_URL}#{quote(name)}",  # 全商品が同一ページのため一意なフラグメントを付ける
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_pengincoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_pengincoffee.json に出力しました")


if __name__ == "__main__":
    main()
