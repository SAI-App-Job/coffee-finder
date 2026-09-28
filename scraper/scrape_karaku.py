# -*- coding: utf-8 -*-
"""
scrape_karaku.py

珈琲焙煎香楽(karaku.shop-pro.jp、福島県いわき市平字五町目6-1 SALON de 蔵
1F、2006年開業の自家焙煎スペシャルティコーヒー専門店。2026-08時点で
カフェ営業は休止、コーヒー豆販売のみ継続)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。

【店舗発見の経緯】
全国再調査(福島県)でgurutto-iwaki.com記事から発見。

【対象商品について】
実データ確認済み(2026-09時点): 「コーヒー豆―ブレンド（200ｇ）」
(cbid=553525)全7件・「コーヒー豆―シングル（200ｇ）」(cbid=558252)
全9件、計16件を対象とする。「お徳用500g」の2カテゴリは200g版と同一
銘柄の大容量版のため対象外。ドリップバッグ・ギフト・器具も対象外。

【商品説明の構造について】
実データ確認済み: シングル商品には`<p>`内に「地　区：」「品　種：」
「標　高：」「精　製：」「乾　燥：」という、ラベルの2文字の間に
全角スペースが挟まる特殊な表記(例:「地　区」)があり、`<br />`区切りで
並ぶ。ブレンド商品にはこの構造化ラベルが無く自由記述のみ。

【文字コード】EUC-JP(実データ確認済み)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method

SHOP_INFO = {
    "name": "珈琲焙煎香楽",
    "url": "https://karaku.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "福島県いわき市平字五町目6-1 SALON de 蔵1F",
    "prefecture": "福島県",
    "robots_txt_status": "許可(2026-09確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://karaku.shop-pro.jp/"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (CoffeeFinderBot/0.1; +contact: your-contact-info-here)"}
CATEGORY_IDS = ["553525", "558252"]  # ブレンド200g, シングル200g

LABEL_MAP = {"地区": "地区", "地域": "地区", "品種": "品種", "標高": "標高",
             "精製": "精選方法", "乾燥": "乾燥方法", "グレード": "グレード"}
LABEL_PATTERN = re.compile(r"(地\s*区|地\s*域|品\s*種|標\s*高|精\s*製|乾\s*燥|グレード)\s*[：:]\s*")


def fetch_euc(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "euc-jp"
    return resp.text


def collect_product_ids() -> list[str]:
    ids = []
    for cbid in CATEGORY_IDS:
        html = fetch_euc(f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0")
        soup = BeautifulSoup(html, "html.parser")
        for li in soup.select("li.productlist_list"):
            a = li.select_one("a[href*=pid]")
            if a:
                m = re.search(r"pid=(\d+)", a["href"])
                if m:
                    ids.append(m.group(1))
    return ids


def build_record(pid: str) -> dict | None:
    html = fetch_euc(f"{BASE_URL}?pid={pid}")
    m = re.search(r"var\s+Colorme\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    colorme = json.loads(m.group(1))
    product = colorme.get("product") or {}
    title = re.sub(r"^■?「", "「", (product.get("name") or "").strip()).strip()
    if not title:
        return None

    soup = BeautifulSoup(html, "html.parser")
    explain = soup.select_one("div.product_explain")
    labels = {}
    flavor_notes = None
    if explain:
        for br in explain.find_all("br"):
            br.replace_with("\n")
        text = explain.get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        intro_lines = []
        for line in lines:
            lm = LABEL_PATTERN.match(line)
            if lm:
                normalized_label = re.sub(r"\s", "", lm.group(1))
                key = LABEL_MAP[normalized_label]
                value = line[lm.end():].strip()
                labels[key] = value
            else:
                intro_lines.append(line)
        flavor_notes = "\n".join(intro_lines) or None

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax")
    stock_num = product.get("stock_num")
    sold_out = isinstance(stock_num, int) and stock_num <= 0
    stock_status = "完売" if sold_out else "販売中"

    url = f"{BASE_URL}?pid={pid}"
    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": url,
        }

    region = labels.get("地区")
    detected = (region and detect_country_name(region)) or detect_country_name(title)
    if detected:
        parsed["origin_country"] = detected
        parsed["origin_source"] = "product_description" if region else "raw_name"
    parsed = apply_category_hint_fallback(parsed, title)

    if labels.get("精選方法"):
        parsed["processing_method"] = normalize_processing_method(labels["精選方法"])

    farm_parts = [f"{k}: {labels[k]}" for k in ("地区", "品種", "標高", "乾燥方法", "グレード") if labels.get(k)]
    farm_note = "、".join(farm_parts) if farm_parts else None

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
        "price": price,
        "weight_g": 200,
        "stock_status": stock_status,
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    records = []
    flavored_records = []
    for pid in collect_product_ids():
        try:
            detail = build_record(pid)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={pid} ({e})")
            continue
        if detail is None:
            continue
        (flavored_records if detail.get("is_flavored") else records).append(detail)
    return records, flavored_records


def main():
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_karaku.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_karaku.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
