# -*- coding: utf-8 -*-
"""
scrape_86coffee.py

86 COFFEE ROASTERS(86coffeeroasters.com、埼玉県川口市川口4-2-4 アイビービル
101、川口駅西口徒歩3分、フジローヤルR-103で自家焙煎の単独1店舗)の商品情報を
取得する。Jimdo Shop。

【店舗発見の経緯】
2026-09-04の別セッションで「Jimdo組み込みの通販機能の商品一覧の確認に
時間を要する」として見送られていたが、全国再調査(埼玉県)で再検証し、
商品一覧ページ(/コーヒー豆等の通信販売/)から個別ページ(/<slug>/)をたどれば
plain requestsで全商品の価格・焙煎度・産地が取得できることを確認して実装した。
(`/j/shop/`直下は404。一覧ページのURLは日本語のため percent-encode が必要。)

【対象商品について】
実データ確認済み(2026-10時点): 一覧に10商品(豆9銘柄+アソートドリップバッグ)。
ドリップバッグを除いた豆9銘柄(ブレンド2・ストレート7、デカフェ1含む)を
対象とする。各銘柄は100g/250g/500gの3サイズ展開のため、他店舗と同様に
最小の100gの価格を代表として収録する。支払いは銀行振込のみ。

【ページ構造について】
実データ確認済み: テキスト化すると「生産国：」「焙煎度合い：」「精選処理：」
「100g:1,140円」(全角の「100ｇ：」の場合あり)「在庫あり/在庫切れ」の各行が
並ぶ。商品名は<title>の「<商品名> - 86coffeeroasters ページ！」から取得する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "86 COFFEE ROASTERS",
    "url": "https://86coffeeroasters.com/",
    "platform": "Jimdo Shop",
    "address": "埼玉県川口市川口4-2-4 アイビービル101",
    "prefecture": "埼玉県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://86coffeeroasters.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

SLUGS = [
    "86house-blend",
    "geisha-blend",
    "chiapas-decafe",
    "narino-tropico-sur",
    "cachoeira-da-grama",
    "mandheling-tobako",
    "yirgacheffe-kochere",
    "karindundu",
    "ngera-anaerobic",
]

TITLE_PATTERN = re.compile(r"<title>([^<]+?)\s*-\s*86coffeeroasters")
PRICE_100G_PATTERN = re.compile(r"^100[gｇ][:：]\s*([\d,]+)円")


def build_record(slug: str) -> dict | None:
    url = f"{BASE_URL}/{slug}/"
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    resp.encoding = "utf-8"
    title_m = TITLE_PATTERN.search(resp.text)
    if not title_m:
        return None
    name = title_m.group(1).strip()

    lines = [ln.strip() for ln in BeautifulSoup(resp.text, "html.parser").get_text("\n", strip=True).split("\n") if ln.strip()]

    country_line = next((ln for ln in lines if ln.startswith("生産国：")), "")
    roast_line = next((ln for ln in lines if ln.startswith("焙煎度合い：")), "")
    process_line = next((ln for ln in lines if ln.startswith("精選処理：")), "")
    price = None
    for ln in lines:
        m = PRICE_100G_PATTERN.match(ln)
        if m:
            price = int(m.group(1).replace(",", ""))
            break
    out_of_stock = any(ln in ("在庫切れ", "売り切れ", "SOLD OUT") for ln in lines)

    # 説明文: 「生産国：」行より後ろ〜「焙煎度合い：」行の手前(カッピングノートを含む)
    desc = None
    if country_line and roast_line:
        start = lines.index(country_line) + 1
        end = lines.index(roast_line)
        desc = " ".join(lines[start:end]).strip() or None

    parsed = parse_product(name)
    country_text = country_line.replace("生産国：", "")
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        detected = detect_country_name(country_text) or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, country_text)

    processing = parsed["processing_method"] or detect_processing_method(process_line.replace("精選処理：", ""))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": roast_line.replace("焙煎度合い：", "") or parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": 100,
        "stock_status": "完売" if out_of_stock else "販売中",
        "out_of_stock": out_of_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for slug in SLUGS:
        try:
            detail = build_record(slug)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {slug} ({e})")
            continue
        if detail is not None:
            records.append(detail)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_86coffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_86coffee.json に出力しました")


if __name__ == "__main__":
    main()
