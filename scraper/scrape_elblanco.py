# -*- coding: utf-8 -*-
"""
scrape_elblanco.py

COFFEE ROAST EL BLANCO(en.el-blanco.com、東京都品川区旗の台5-8-7、運営: ストレダ合同会社、
店内の焙煎機で焙煎する自家焙煎店、店頭受け取りも可、単独1店舗)の商品情報を取得する。
Wix(Wix Stores)。

【ページ構造について】
実データ確認済み(2026-10時点): `/store-products-sitemap.xml`から全79商品ページURLを列挙し、
各商品ページのJSON-LD(schema.org Product)から名前・説明・価格・在庫を、本文の
「【内容量】220gの生豆を焙煎した後…」から重量(生豆重量)を取得する。
(以前の見送り理由だった一覧ページの断片的なJS変数は使わず、商品ページ単位で取得する。)

【対象商品について】
ドリップバッグ・各種ギフト/セット・飲み比べ・ラッピング資材・キャンバスアート・器具
(カリタ簡単ドリップ)・レターコーヒー・「豆が選べる」セットは除外し、焙煎豆(ストレート
およびブレンド、デカフェ含む)のみを対象とする。重量は商品ページの「【内容量】」の
生豆グラム数(多くは220g、焙煎後およそ180〜190g)で、一部の商品のみ別重量
(例: 「エキゾチック ストロベリーハニー」200g)。
産地は「【原産国】」欄の記載を優先し、「ブレンド」を含む名称や複数国表記の商品は
category「ブレンド」とする。焙煎度は購入時オプション(おまかせ)のため商品名・説明に
記載がある場合のみ取得する。
"""

import html
import json
import re
import unicodedata
from urllib.parse import unquote

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "COFFEE ROAST EL BLANCO",
    "url": "https://en.el-blanco.com/",
    "platform": "Wix(Wix Stores)",
    "address": "東京都品川区旗の台5-8-7",
    "prefecture": "東京都",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://en.el-blanco.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

LD_PATTERN = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
EXCLUDE_KEYWORDS = (
    "ドリップバック", "DRIP BAG", "ドリップバッグ", "ギフト", "set", "SET", "セット", "飲み比べ", "ラッピング",
    "キャンバスアート", "カリタ", "レターコーヒー", "選べる",
)
WEIGHT_PATTERN = re.compile(r"【内容量】\s*(\d+)\s*g")
ORIGIN_FIELD_PATTERN = re.compile(r"【原産国】\s*([^\n【]*)")

session = requests.Session()
session.headers.update(REQUEST_HEADERS)


def list_product_urls() -> list[str]:
    resp = session.get(f"{BASE_URL}/store-products-sitemap.xml", timeout=30)
    return re.findall(r"<loc>([^<]+)</loc>", resp.text)


def clean_name(text: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(text))
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def build_record(url: str) -> dict | None:
    resp = session.get(url, timeout=30)
    resp.encoding = "utf-8"
    ld_m = LD_PATTERN.search(resp.text)
    if not ld_m:
        return None
    ld = json.loads(ld_m.group(1))
    full_name = clean_name(ld.get("name", ""))
    if any(kw in full_name for kw in EXCLUDE_KEYWORDS):
        return None

    # 本文テキスト(スクリプト・タグ除去)から重量・原産国を取得
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", resp.text, flags=re.S)
    body = html.unescape(re.sub(r"<(?:br|/p|/div|/li)[^>]*>", "\n", body))
    body = re.sub(r"<[^>]+>", "", body)
    weight_m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", body))
    if not weight_m:  # 豆商品には必ず「【内容量】…g」がある(無いものは豆以外)
        return None
    weight_g = int(weight_m.group(1))
    origin_m = ORIGIN_FIELD_PATTERN.search(unicodedata.normalize("NFKC", body))
    origin_field = origin_m.group(1).strip() if origin_m else ""

    # 名称: 末尾の「[ ブラジル産 ]」表記はそのまま産地表示として残す(角括弧内の空白のみ整形)
    name = re.sub(r"\[\s*", "[", full_name)
    name = re.sub(r"\s*\]", "]", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s*豆?\d+g$", "", name)  # 末尾の重量表記(「豆220g」「200g」)は weight_g に反映済みのため除去

    desc = re.sub(r"\s+", " ", html.unescape(ld.get("description") or "")).strip()[:500] or None
    offer = ld.get("offers") or {}
    if isinstance(offer, list):
        offer = offer[0] if offer else {}
    price = int(float(offer["price"])) if offer.get("price") else None
    in_stock = "InStock" in (offer.get("availability") or "")

    parsed = parse_product(name)
    countries = [c for c in re.split(r"[・,、/]|他", origin_field) if c.strip()]
    is_blend = "ブレンド" in name or "ブレンド" in origin_field or len(countries) > 1 or origin_field.endswith("他")
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            detected = detect_country_name(origin_field) or detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name + " " + origin_field)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"] or detect_processing_method(name),
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": None,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for url in list_product_urls():
        try:
            record = build_record(url)
        except (requests.RequestException, ValueError) as e:
            print(f"[warn] 商品ページ取得失敗: {unquote(url)} ({e})")
            continue
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_elblanco.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_elblanco.json に出力しました")


if __name__ == "__main__":
    main()
