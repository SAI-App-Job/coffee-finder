# -*- coding: utf-8 -*-
"""
scrape_luontocoffee.py

LUONTOCOFFEE(ルオントコーヒー、luontocoffee.com、愛知県岡崎市大和町字塗御堂40-1)の
オンラインショップの商品情報を取得する。WordPress + WooCommerce(Store API
/wp-json/wc/store/v1/products)。

【アクセス状況】
過去の調査では「クラウドIPで403」とされていたが、2026-10時点のローカル環境からの確認では
Store APIは200で取得できた(User-Agent明示)。実行環境によっては403になる可能性がある。

【対象商品について】
実データ確認済み: Store API全148商品のうち、バリエーション属性「グラム数」(100g/200g)を
持つ焙煎豆商品(シングルオリジン・ブレンド・カフェインレス)を対象とする。
定期便・セット商品・ギフト・ドリップバッグ・水出しバッグ・お楽しみBOX・KUTEのおやつ箱・
器具・雑貨は除外。過去の限定入荷品の多くは在庫切れ(完売)のまま掲載されており、
在庫切れも「完売」として収録する。

【重量・価格・在庫】
各商品のバリエーション(`?type=variation`でなく`/products/<variation_id>`)を取得し、
最小グラム数(通常100g)のバリエーションのうち最安の価格を代表とする。在庫は、その最小
グラム数のバリエーションのいずれかが在庫ありなら「販売中」。味わいの説明文は商品ページ
本文の冒頭部分から取得する。焙煎度の明記はない(カフェインレスのみ「バランス/深煎り」の
選択肢あり)ため、roast_levelはnullとし、「テイストで選ぶ」カテゴリ(ライトテイスト/
バランス型/濃いめ、苦め)をroast_hintとして保持する。
"""

import html
import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "LUONTOCOFFEE",
    "url": "https://luontocoffee.com/",
    "platform": "WordPress + WooCommerce",
    "address": "愛知県岡崎市大和町字塗御堂40-1",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://luontocoffee.com"
API_URL = f"{BASE_URL}/wp-json/wc/store/v1/products"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
WEIGHT_ATTR = "グラム数"
EXCLUDE_CATS = ("定期便", "セット商品", "ギフトセット", "箱ギフト", "100%specialtycoffeeドリップバッグ",
                "お楽しみBOX", "KUTEのおやつ箱", "コーヒー器具", "水出しコーヒー", "ラッピングオプション")
EXCLUDE_WORDS = ("定期便", "セット", "ギフト", "ドリップバッグ", "水出し", "お楽しみ", "おやつ箱")
ORIGIN_OVERRIDES = {"ジンバブエ": "ジンバブエ", "タイ ": "タイ", "タイ・": "タイ"}  # coffee_parserの国名辞書にない産地
TASTE_CATS = ("ライトテイスト", "バランス型", "濃いめ、苦め")


def fetch_products() -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        resp = requests.get(API_URL, params={"per_page": 100, "page": page}, headers=REQUEST_HEADERS, timeout=30)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return products


def clean_name(raw: str) -> str:
    n = html.unescape(raw).replace("　", " ")
    n = re.sub(r"〈[^〉]*〉", " ", n)
    n = re.sub(r"[【\[［《≪][^】\]］》≫]*(限定|入荷|ブレンド)[^】\]］》≫]*[】\]］》≫]", " ", n)
    n = re.sub(r"\d+\s*g\s*or\s*\d+\s*g|100\s*or\s*200g", " ", n)
    n = re.sub(r"[（(]次回入荷予定[^）)]*[）)]", " ", n)
    n = re.sub(r"［[^］]*(自家焙煎|コーヒー)[^］]*］", " ", n)
    n = re.sub(r"【カフェインレス】", "カフェインレス ", n)
    n = re.sub(r"\s*\d+\s*g\s*$", "", n.strip())
    return re.sub(r"\s+", " ", n).strip()


def page_description(permalink: str) -> str | None:
    try:
        r = requests.get(permalink, headers=REQUEST_HEADERS, timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return None
    s = BeautifulSoup(r.text, "html.parser")
    for t in s(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    lines = [ln for ln in s.get_text("\n", strip=True).split("\n") if ln]
    # 先頭行は「<title> | LUONTOCOFFEE」。価格表示(「￥」)の手前までが商品紹介文
    out = []
    for ln in lines[1:]:
        if ln.startswith("￥") or ln.startswith("原産国名") or ln.startswith("≪ドリップ"):
            break
        out.append(ln)
    text = re.sub(r"\s+", " ", " ".join(out)).strip()
    return text[:300] or None


def min_weight_variant(p: dict) -> tuple[int | None, int | None, bool]:
    """(重量g, 価格, 在庫あり) を返す。"""
    variations = p.get("variations") or []
    weighted = []
    for v in variations:
        w = next((a["value"] for a in v["attributes"] if a["name"] == WEIGHT_ATTR and a["value"]), None)
        m = re.match(r"(\d+)\s*g", w or "")
        if m:
            weighted.append((int(m.group(1)), v["id"]))
    if not weighted:
        wm = re.search(r"(\d+)\s*g\s*$", html.unescape(p["name"]).strip())
        price = int(p["prices"]["price"]) if p["prices"].get("price") else None
        return (int(wm.group(1)) if wm else None), price, bool(p.get("is_in_stock"))
    min_w = min(w for w, _ in weighted)
    prices, in_stock = [], False
    for w, vid in weighted:
        if w != min_w:
            continue
        r = requests.get(f"{API_URL}/{vid}", headers=REQUEST_HEADERS, timeout=30)
        r.raise_for_status()
        vd = r.json()
        prices.append(int(vd["prices"]["price"]))
        in_stock = in_stock or bool(vd.get("is_in_stock"))
        time.sleep(0.2)
    return min_w, min(prices), in_stock


def build_record(p: dict) -> dict | None:
    cats = [html.unescape(c["name"]) for c in p.get("categories") or []]
    name_raw = html.unescape(p["name"])
    if any(c in EXCLUDE_CATS for c in cats) or any(w in name_raw for w in EXCLUDE_WORDS):
        return None
    if not any(a["name"] == WEIGHT_ATTR for a in p.get("attributes") or []):
        return None

    weight, price, in_stock = min_weight_variant(p)
    name = clean_name(name_raw)
    is_blend = "ブレンド" in name or "定番ブレンド" in cats or "限定ブレンド" in cats
    taste = next((c for c in cats if c in TASTE_CATS), None)

    parsed = parse_product(name)
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["processing_method"] = None
    else:
        parsed["category"] = "ストレート"
        detected = detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "country_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if name.startswith(kw):
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break

    desc = BeautifulSoup(p.get("short_description") or "", "html.parser").get_text(" ", strip=True)
    desc = re.sub(r"\s+", " ", desc).strip() or page_description(p["permalink"])
    time.sleep(0.2)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": taste,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": p["permalink"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for p in fetch_products():
        rec = build_record(p)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_luontocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_luontocoffee.json に出力しました")


if __name__ == "__main__":
    main()
