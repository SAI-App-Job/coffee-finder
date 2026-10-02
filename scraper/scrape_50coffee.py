# -*- coding: utf-8 -*-
"""
scrape_50coffee.py

50 COFFEE & ROASTERY(50coffeeandroastery.com、埼玉県深谷市深谷町9-12、旧中山道沿い
の七ツ梅酒造跡地で自家焙煎)の商品情報を取得する。カラーミーショップ
(charset=euc-jpのレガシーページのため`r.encoding = "euc-jp"`を明示する)。

【店舗発見の経緯】
全国再調査(埼玉県)の新規発掘で発見。

【対象商品について】
実データ確認済み(2026-10時点): 「Coffee beans」(cbid=2582187)・
「Decaf」(cbid=2830711)の2カテゴリを対象とし、コーヒーバッグ・ギフトセット・
ドリップバッグ等の別形態は商品名のキーワードで除外する。
商品名・価格・説明はog:title/product:price:amount/og:descriptionから取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "50 COFFEE & ROASTERY",
    "url": "https://50coffeeandroastery.com/",
    "platform": "カラーミーショップ",
    "address": "埼玉県深谷市深谷町9-12",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://50coffeeandroastery.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
CATEGORY_IDS = ["2582187", "2830711"]
EXCLUDE_KEYWORDS = ("バッグ", "ギフト", "セット", "ドリップ", "フィルター", "リキッド", "ベース")

TITLE_PATTERN = re.compile(r'<meta property="og:title" content="([^"]*)"')
PRICE_PATTERN = re.compile(r'product:price:amount" content="(\d+)"')


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.encoding = "euc-jp"
    return resp.text


def list_product_ids() -> list[str]:
    ids: list[str] = []
    for cbid in CATEGORY_IDS:
        html_text = fetch(f"{BASE_URL}/?mode=cate&cbid={cbid}&csid=0")
        for pid in re.findall(r"pid=(\d+)", html_text):
            if pid not in ids:
                ids.append(pid)
    return ids


def build_record(pid: str) -> dict | None:
    html_text = fetch(f"{BASE_URL}/?pid={pid}")
    title_m = TITLE_PATTERN.search(html_text)
    if not title_m:
        return None
    title = re.sub(r"\s+", " ", title_m.group(1).split(" - 50 Coffee")[0]).strip()
    title = title.replace("&amp;", "&")
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    price_m = PRICE_PATTERN.search(html_text)

    # 商品本文(og:descriptionは全商品共通の店舗紹介文のため使わない)
    body_text = BeautifulSoup(html_text, "html.parser").get_text("\n", strip=True)
    lines = [ln.strip() for ln in body_text.split("\n") if ln.strip()]

    def after(label: str) -> str | None:
        for i, ln in enumerate(lines):
            if ln == label and i + 1 < len(lines):
                return lines[i + 1]
        return None

    taste = after("テイスト")
    country_text = after("生産国")
    farm_bits = [f"{label}:{value}" for label in ("地域", "農園", "標高", "品種", "生産処理") if (value := after(label))]
    desc_parts = ([f"テイスト:{taste}"] if taste else []) + farm_bits
    if "商品詳細" in lines:
        idx = lines.index("商品詳細")
        story = next((ln for ln in lines[idx:] if len(ln) > 60), None)
        if story:
            desc_parts.append(story[:300])
    desc = " / ".join(desc_parts) or None

    weight_g = None
    for ln in lines:
        m = re.match(r"^(\d+)g\s+[\d,]+円", ln)
        if m:
            weight_g = int(m.group(1))
            break

    parsed = parse_product(title)
    if parsed["category"] != "ブレンド":
        detected = detect_country_name(title)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, title)
        if not parsed["origin_country"] and country_text:
            parsed["origin_country"] = detect_country_name(country_text) or country_text
            parsed["origin_source"] = "country_name"
    else:
        parsed["origin_country"] = None
        parsed["origin_source"] = None

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
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price_m.group(1)) if price_m else None,
        "weight_g": weight_g,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": f"{BASE_URL}/?pid={pid}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_product_ids():
        try:
            record = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_50coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_50coffee.json に出力しました")


if __name__ == "__main__":
    main()
