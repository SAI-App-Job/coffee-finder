# -*- coding: utf-8 -*-
"""
scrape_cafegaro.py

自家焙煎珈琲ガロ(cafegaro.com、京都府京都市北区紫野南舟岡町71-27、
自家焙煎豆のオンライン販売)の商品情報を取得する。MakeShop(EUC-JP
エンコーディング)。

【店舗発見の経緯】
京都エリアの空白地調査(kyotopi.jp「珈琲に携わって40年余☆...」)で発見。
1977年創業、2004年に西陣へ移転した老舗。

【対象商品について】
実データ確認済み(全商品一覧all_items、12ページ、生SKU数114件、2026-09
時点): ドリップバッグ各種(5件)を除く全銘柄が100g/200g(一部50g)の重量
違いで複数SKUに分割され、さらに「＊クリックポスト配送商品」という配送
方法違いの重複SKUも存在する。重量表記・クリックポスト注記を除いた銘柄名
でグルーピングし、最小重量側のSKUを代表として1件にまとめる(約40銘柄:
ストレート約30・ブレンド約10)。一覧ページ(all_items/pageN/)自体に全SKUの
商品名が掲載されているため、まず一覧から代表SKUを特定し、その詳細ページ
のみを取得することで114回ではなく約40回のリクエストで済ませている。

【商品説明の構造について】
実データ確認済み: og:descriptionが「豆の特徴：香り/コク/酸味/苦み/甘みの
記号評価(☆◎△等、除去)→(産地情報がある場合のみ)焙煎：/産地：/農園：の
ラベル→テイスティング文→こちらの商品は◯◯g入りです、以降の重量・付属品
案内定型文(除去)」という構成。

【エンコーディングについて】
実データ確認済み: EUC-JPページのためrequests取得時にr.encoding="euc-jp"
の明示が必要。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)

SHOP_INFO = {
    "name": "自家焙煎珈琲ガロ",
    "url": "https://www.cafegaro.com/",
    "platform": "MakeShop",
    "address": "京都府京都市北区紫野南舟岡町71-27",
    "prefecture": "京都府",
    "robots_txt_status": "未確認(MakeShop標準構成を想定)",
}

BASE_URL = "https://www.cafegaro.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]", re.IGNORECASE)
STRIP_PATTERN = re.compile(r"[　\s]*\d+\s*[gｇ]入\s*(?:＊クリックポスト配送商品)?\s*$", re.IGNORECASE)
LABEL_PATTERN = re.compile(r"(焙煎|産地|農園)\s*[：:]\s*([^\n]*)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def fetch_listing() -> list[dict]:
    items = []
    seen_pids = set()
    for page in range(1, 20):
        text = fetch(f"{BASE_URL}/shopbrand/all_items/page{page}/")
        soup = BeautifulSoup(text, "html.parser")
        links = soup.select('a[href*="/shopdetail/"]')
        if not links:
            break
        found_new = False
        for a in links:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            m = re.search(r"/shopdetail/(\d+)/", href)
            if not title or not m:
                continue
            pid = m.group(1)
            if pid in seen_pids:
                continue
            seen_pids.add(pid)
            found_new = True
            weight_m = WEIGHT_PATTERN.search(title)
            items.append({
                "pid": pid, "title": title,
                "weight_g": int(weight_m.group(1)) if weight_m else None,
            })
        if not found_new:
            break
    return items


def dedupe_by_base_name(items: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        base = STRIP_PATTERN.sub("", item["title"])
        base = re.sub(r"[　\s]+", "", base)
        groups.setdefault(base, []).append(item)

    result = []
    for group in groups.values():
        group.sort(key=lambda x: x["weight_g"] or float("inf"))
        result.append(group[0])
    return result


def parse_desc(desc: str) -> tuple[str | None, dict]:
    labels = {m.group(1): m.group(2).strip() for m in LABEL_PATTERN.finditer(desc)}
    text = re.sub(r"^豆の特徴[：:][^\n]*\n?", "", desc.strip())
    for key in ("焙煎", "産地", "農園"):
        text = re.sub(rf"{key}\s*[：:][^\n]*\n?", "", text)
    text = re.split(r"こちらの商品は", text)[0].strip()
    return (text or None), labels


def build_record(item: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    text = fetch(f"{BASE_URL}/shopdetail/{item['pid']}/")
    price_m = re.search(r'<meta property="product:price:amount" content="([^"]*)"', text)
    desc_m = re.search(r'<meta property="og:description" content="([^"]*)"', text)
    desc = desc_m.group(1) if desc_m else ""
    url = f"{BASE_URL}/shopdetail/{item['pid']}/"

    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(float(price_m.group(1))) if price_m else None,
            "product_url": url,
        }

    flavor_notes, labels = parse_desc(desc)

    origin_note = labels.get("産地")
    detected = (origin_note and detect_country_name(origin_note)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if origin_note else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("焙煎"):
        roast_parsed = parse_product(labels["焙煎"])
        if roast_parsed.get("roast_level"):
            parsed["roast_level"] = roast_parsed["roast_level"]

    farm_note = labels.get("農園")
    stock_status = detect_stock_status(title)

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
        "farm_note": farm_note,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(float(price_m.group(1))) if price_m else None,
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = fetch_listing()
    items = [i for i in items if not any(kw in i["title"] for kw in NON_BEAN_KEYWORDS)]
    deduped = dedupe_by_base_name(items)

    records = []
    flavored_records = []
    for item in deduped:
        try:
            detail = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_cafegaro.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_cafegaro.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
