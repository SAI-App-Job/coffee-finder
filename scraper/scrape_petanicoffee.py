# -*- coding: utf-8 -*-
"""
scrape_petanicoffee.py

Petani coffee(petanicoffee.com、福岡県糸島市志摩初2-3-11の自家焙煎所「農家のコーヒー」)の商品情報を
取得する。サイトはWordPress(カスタム投稿タイプ beans)で、購入ボタンだけカラーミーショップ
(petani.shop-pro.jp)のカートJSを埋め込む構成。旧 petani.shop-pro.jp は証明書エラーのため使わない
(カートJS・在庫表示は取得しない)。

【対象商品について】
実データ確認済み(2026-10時点): 商品一覧 /beans/beans_type/beans/(2ページ、計15件)のうち、
単品の焙煎豆(シングルオリジン・ブレンド、10件)を対象とする。
次は対象外: 焙煎所おまかせセット・季節のブレンドセット(セット)、水出しコーヒーパック、
アイスコーヒー ゲイシャ種(1000mlのリキッド飲料)、ドリップパック(別カテゴリ)。

【価格・重量・在庫】
価格は一覧/詳細ページの表示価格(税込、例「990円」)。商品ページに重量の明記は無いが、セットの
説明(「オーガニック豆100g×4種 3,890円」等)と「200g以上ご注文の場合」の梱包案内から
1袋100gが販売単位と判断し、重量は100gとする(ページ上の明記は無く、推定)。
在庫表示は旧カラーミーショップのカートJS(証明書エラー)側にしかなく取得できないため、
全商品を「販売中」とする。
焙煎度は商品名先頭の【浅煎り】【中煎り】【中深煎り】【深煎り】、産地・精製方法は詳細欄の
【生産地】【精製方法】から取得する(複数産地は「×」区切りでブレンド扱い)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, extract_from_description,
)

SHOP_INFO = {
    "name": "Petani coffee",
    "url": "https://petanicoffee.com/",
    "platform": "WordPress+カラーミーショップ",
    "address": "福岡県糸島市志摩初2-3-11",
    "prefecture": "福岡県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://petanicoffee.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LIST_URL = BASE_URL + "/beans/beans_type/beans/"
MAX_PAGES = 5
EXCLUDE_KEYWORDS = ("セット", "水出し", "アイスコーヒー", "ドリップ", "ギフト", "生豆", "リキッド")
ROAST_PATTERN = re.compile(r"(中浅煎り|中深煎り|浅煎り|中煎り|深煎り)")
UNIT_WEIGHT_G = 100


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def collect_items() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else f"{LIST_URL}page/{page}/"
        try:
            html = fetch_html(url)
        except requests.HTTPError:
            break
        soup = BeautifulSoup(html, "html.parser")
        found = 0
        for h3 in soup.select("h3.pco-product-title a"):
            href = h3["href"]
            if href not in seen:
                seen.add(href)
                items.append((href, h3.get_text(strip=True)))
                found += 1
        if not found:
            break
    return items


def parse_item(url: str) -> dict | None:
    soup = BeautifulSoup(fetch_html(url), "html.parser")
    main = soup.select_one("main") or soup
    for s in main(["script", "style"]):
        s.decompose()
    h = main.select_one("h1, h2.entry-title") or None
    lines = [l.strip() for l in main.get_text("\n", strip=True).split("\n") if l.strip()]
    price_idx = next((i for i, l in enumerate(lines) if re.fullmatch(r"[\d,]+円", l)), None)
    if price_idx is None:
        return None
    price = int(lines[price_idx].replace(",", "").replace("円", ""))
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", lines[price_idx - 1])).strip()
    if any(k in title for k in EXCLUDE_KEYWORDS):
        return None

    body_lines = []
    for l in lines[price_idx + 1:]:
        if l.startswith("──") or l.startswith("※包装") or l == "一覧に戻る":
            break
        body_lines.append(l)
    body = "\n".join(body_lines)
    fields = {}
    cur = None
    for l in body_lines:
        fm = re.match(r"【(生産地|農園|樹種|精製方法|乾燥方法|その他情報)】\s*(.*)", l)
        if fm:
            cur = fm.group(1)
            fields[cur] = fm.group(2).strip()
        elif cur and not l.startswith("【") and not fields.get(cur):
            fields[cur] = l.strip()
    # 説明文: 【生産地】等の詳細欄より前(「以下詳細情報です。」は除く)
    desc_lines = []
    for l in body_lines:
        if l.startswith("【") or l.startswith("以下詳細"):
            break
        desc_lines.append(l)
    flavor_notes = re.sub(r"\s+", " ", " ".join(desc_lines))[:400] or None

    parsed = parse_product(title)
    is_blend = "ブレンド" in title
    origin_field = fields.get("生産地", "")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
        parsed["processing_method"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"] and origin_field:
            c = detect_country_name(origin_field)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "description"
        parsed = apply_category_hint_fallback(parsed, title)
        if not parsed["processing_method"] and fields.get("精製方法"):
            parsed["processing_method"] = extract_from_description("精製方法：" + fields["精製方法"])["processing_method"]

    rm = ROAST_PATTERN.search(title)
    roast_level = rm.group(1) if rm else parsed["roast_level"]
    farm = None if is_blend else fields.get("農園")

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": roast_level,
        "flavor_notes": flavor_notes,
        "farm_note": farm,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": UNIT_WEIGHT_G,
        "stock_status": "販売中",
        "out_of_stock": False,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url, list_title in collect_items():
        if any(k in list_title for k in EXCLUDE_KEYWORDS):
            continue
        rec = parse_item(url)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_petanicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_petanicoffee.json に出力しました")


if __name__ == "__main__":
    main()
