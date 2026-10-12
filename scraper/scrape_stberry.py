# -*- coding: utf-8 -*-
"""
scrape_stberry.py

セントベリーコーヒー(stberry.net、富山県魚津市、おちゃのこネット(Ocnk))の
自家焙煎コーヒー豆の商品情報を取得する。

robots.txt確認済み(2026-10): GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ
Disallow: /、それ以外は制限なし。

【商品の取得方法】
全商品一覧(/product-list)は40件(ドリップバッグ・セット・送料・お菓子等を含む)で
ページ送りは無い(件数表示40件、/photo/2等も同一内容)。コーヒー豆は味わい別カテゴリ
(200 季節のブレンド、209 芳醇、210 軽やか、211 爽やか、212 個性的、9 品評会入賞豆)に
属するため、そのカテゴリ一覧から商品URLを集める(ドリップバッグ・セット・水出しバッグ・
リキッド・ギフト包装・お菓子は含まれない)。

【価格・重量】
容量バリエーション(100g/250g/500g)ごとに価格が異なる(税別表示)。最小重量(通常100g)
のバリエーションを代表とし、税込価格(#tax_included_price の最小値=最小容量、
税別×1.08と一致を確認)を採用する。トヤマブレンドは500gのみ。

【在庫】
在庫は容量×挽き方のマトリクス(pConf.zaikoArray、在庫数)で、「豆のまま」が0で
挽き済みのみ在庫ありの銘柄がある。最小容量のいずれかの挽き方で在庫>0なら販売中、
在庫がマトリクスに無い(無制限)場合も販売中、購入フォームが無い商品は品切れ扱い。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_country_name,
)

SHOP_INFO = {
    "name": "セントベリーコーヒー",
    "url": "https://stberry.net/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "富山県魚津市本江1330-1",
    "prefecture": "富山県",
    "robots_txt_status": "実質許可(2026-10確認。GPTBot等AI系ボットのみ個別にDisallow: /、"
                          "それ以外は制限なし)",
}

BASE_URL = "https://www.stberry.net"
CATEGORY_IDS = [200, 209, 210, 211, 212, 9]
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
NON_BEAN_KEYWORDS = ["ドリップ", "セット", "水だし", "水出し", "リキッド", "ギフト", "送料", "COLD BREW"]

ROAST_PATTERN = re.compile(r"焙煎度合\s*[◆◇■]?\s*([^\s■【]+)")
COUNTRY_PATTERN = re.compile(r"国[:：]\s*(\S+)")
PROCESS_PATTERN = re.compile(r"精製方法[:：]\s*(\S+)")
VARIETY_PATTERN = re.compile(r"品種[:：]\s*(.+?)\s*(?:精製方法|■|$)")
FARM_PATTERN = re.compile(r"農園[:：]\s*(.+?)\s*農園主")
TASTING_PATTERN = re.compile(r"テイスティングコメント\s*(.+?)\s*焙煎度合", re.DOTALL)
NUM = re.compile(r"[\d,]+")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser"), resp.text


def fetch_product_urls() -> list[str]:
    urls = []
    for cid in CATEGORY_IDS:
        soup, _ = fetch_page(f"{BASE_URL}/product-list/{cid}")
        for a in soup.select("a.item_data_link"):
            href = a.get("href")
            if href and re.search(r"/product/\d+$", href):
                href = re.sub(r"^https?://(www\.)?stberry\.net", BASE_URL, href)
                if href not in urls:
                    urls.append(href)
        time.sleep(CRAWL_DELAY_SECONDS)
    return urls


def weight_to_g(label: str) -> int | None:
    m = re.search(r"(\d+)\s*(kg|g)", label, re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)


def parse_detail(url: str) -> dict | None:
    soup, html = fetch_page(url)
    title_el = soup.select_one('meta[property="og:title"]')
    title = (title_el["content"] if title_el else soup.title.get_text().split(" - ")[0]).strip()
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    # 容量バリエーション
    weights = {}
    for lab in soup.select(".variation_label"):
        if lab.get_text(strip=True) == "容量":
            box = lab.find_parent(class_="item_box")
            for opt in box.select("option"):
                if opt.get("value"):
                    weights[opt["value"]] = weight_to_g(opt.get_text(strip=True))
    weights = {k: v for k, v in weights.items() if v}
    min_weight = min(weights.values()) if weights else None
    min_ids = [k for k, v in weights.items() if v == min_weight]

    # 税込価格(最小=最小容量)
    ti = soup.select_one("#tax_included_price")
    price = None
    if ti:
        m = NUM.search(ti.get_text())
        if m:
            price = int(m.group(0).replace(",", ""))
    else:
        pm = soup.select_one('meta[property="product:price:amount"]')
        if pm:
            price = int(float(pm["content"]))

    # 在庫
    has_form = soup.select_one("#productadd") is not None and bool(soup.select("select[name^=cart_addvariant]")) \
        or soup.select_one('input[name^="cart_add_"]') is not None
    stocks = re.findall(r"zaikoArray\[\d+\]\[(\d+)\]\[\d+\] = (\d+);", html)
    if not has_form:
        stock_status = "一時的に品切れ"
    elif stocks:
        rel = [int(n) for vid, n in stocks if (not min_ids or vid in min_ids)]
        stock_status = "販売中" if any(n > 0 for n in rel) else "一時的に品切れ"
    else:
        stock_status = "販売中"
    if "SOLD OUT" in soup.get_text() and not has_form:
        stock_status = "一時的に品切れ"

    desc_el = soup.select_one(".item_desc_text")
    desc = re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)) if desc_el else ""
    roast_m = ROAST_PATTERN.search(desc)
    country_m = COUNTRY_PATTERN.search(desc)
    process_m = PROCESS_PATTERN.search(desc)
    variety_m = VARIETY_PATTERN.search(desc)
    farm_m = FARM_PATTERN.search(desc)
    tasting_m = TASTING_PATTERN.search(desc)
    flavor_notes = None
    if tasting_m:
        flavor_notes = tasting_m.group(1).strip()
        # 先頭の英語名・日本語名の重複(例: "Kenya Kirinyaga ケニア キャリニガ")を除く
        flavor_notes = flavor_notes or None
    elif desc:
        flavor_notes = desc

    return {
        "title": title, "price": price, "weight": min_weight, "stock_status": stock_status,
        "roast_hint": roast_m.group(1) if roast_m else None,
        "country": country_m.group(1) if country_m else None,
        "process": process_m.group(1) if process_m else None,
        "variety": variety_m.group(1) if variety_m else None,
        "farm": farm_m.group(1) if farm_m else None,
        "flavor_notes": flavor_notes, "url": url,
    }


def build_record(d: dict) -> dict:
    title = d["title"]
    parsed = parse_product(title)
    if parsed["is_flavored"]:
        return {"shop_name": SHOP_INFO["name"], "raw_name": title, "category": "フレーバー",
                "is_flavored": True, "flavor_name": parsed["flavor_name"],
                "price": d["price"], "product_url": d["url"]}
    if parsed["category"] != "ブレンド":
        if not parsed["origin_country"]:
            c = d.get("country") or detect_country_name(title)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if d.get("process") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(d["process"])
    parsed = apply_category_hint_fallback(parsed, None)
    farm_parts = []
    if d.get("farm"):
        farm_parts.append(f"農園: {d['farm']}")
    if d.get("variety"):
        farm_parts.append(f"品種: {d['variety']}")
    stock_status = d["stock_status"]
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
        "roast_hint": d.get("roast_hint"),
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": d.get("flavor_notes"),
        "blend_components": [],
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": d["url"],
    }


def scrape_all_products():
    records, flavored = [], []
    for url in fetch_product_urls():
        try:
            d = parse_detail(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if not d:
            continue
        rec = build_record(d)
        (flavored if rec.get("is_flavored") else records).append(rec)
    return records, flavored


if __name__ == "__main__":
    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records, "flavored_products_excluded": flavored}
    with open("data_stberry.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_stberry.json に出力しました(フレーバー{len(flavored)}件は別枠)")
