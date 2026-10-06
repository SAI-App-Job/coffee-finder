# -*- coding: utf-8 -*-
"""
scrape_mameyamato.py

珈琲豆屋 大和(mameyamato.shop-pro.jp、公式サイト https://mameyamato.com/、広島県広島市安佐南区安東の
自家焙煎珈琲豆店)の商品情報を取得する。カラーミーショップ(shop-pro.jpドメイン、文字コードEUC-JP)。

【店舗発見の経緯】
全国再調査(広島県)の新規発掘で発見。

【住所について】
特定商取引法に基づく表記(?mode=sk)で実データ確認済み(2026-10時点): 「珈琲豆屋大和
郵便番号 731-0153 住所 広島県広島市安佐南区安東2-2-5」。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「珈琲豆」(cbid=1538105、全39商品・4ページ)のうち、
焙煎豆(ブレンド約19・ストレート約13・カフェインレス1=33件)を対象とする。
除外: 「おまかせセット」「ギフトセット」(3種)「お試しセット」「???準備中」(13,200円・セット・準備中)。
珈琲器具カテゴリは対象外。各商品は「100g/200g」×「豆のまま/粉に挽く」のバリエーションを持ち、
一覧表示価格は200gの価格。最小重量100g・豆のままのバリエーション価格(200gの半額)を採用する。

【在庫・価格・焙煎度について】
価格は税込。在庫は一覧の「SOLD OUT」表示(商品JSONのstock_num=0)で判定する。
焙煎度は商品説明の「煎り具合 ○○」欄、または商品名の「深煎り/浅煎り/中煎り」を roast_hint に保持する
(「煎り具合」欄・商品名に無い商品は、説明文中の焙煎度表記が1種類のみの場合だけ採用し、それ以外はNone。焙煎度は選択式ではない)。

【robots.txtについて】
User-agent: *はDisallow: /secure/・/cart/のみ(実データ確認済み、2026-10)。商品ページは許可。
"""

import json
import re
import time
import unicodedata

import requests

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈琲豆屋 大和",
    "url": "https://mameyamato.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro)",
    "address": "広島県広島市安佐南区安東2-2-5",
    "prefecture": "広島県",
    "robots_txt_status": "許可(2026-10確認。User-agent: *は/secure/・/cart/のみDisallow)",
}

BASE_URL = "https://mameyamato.shop-pro.jp"
CATEGORY_URL = BASE_URL + "/?mode=cate&cbid=1538105&csid=0&page={page}"
MAX_PAGES = 8
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

ITEM_NAME_PATTERN = re.compile(r'<p class="item_name">\s*<a href="\?pid=(\d+)">(.*?)</a>', re.S)
PRICE_PATTERN = re.compile(r"([\d,]+)円\(税込\)")
COLORME_PATTERN = re.compile(r"var Colorme = (\{.*?\});\s*\n", re.S)
DESC_PATTERN = re.compile(r'<div class="product_description">(.*?)</div>', re.S)
ROAST_LINE_PATTERN = re.compile(r"煎り具合\s*(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
ROAST_NAME_PATTERN = re.compile(r"(中深煎り|中浅煎り|浅煎り|中煎り|深煎り)")
EXCLUDE_KEYWORDS = ["セット", "準備中", "ギフト"]
ORIGIN_OVERRIDES = {"グァテマラ": "グアテマラ"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "euc-jp"
    return re.sub(r"<!--.*?-->", "", resp.text, flags=re.S)


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(1, MAX_PAGES + 1):
        html_text = fetch_html(CATEGORY_URL.format(page=page))
        new = 0
        for block in html_text.split('<div class="item_box')[1:]:
            name_m = ITEM_NAME_PATTERN.search(block)
            if not name_m or name_m.group(1) in items:
                continue
            new += 1
            text = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block.split("item_detail")[-1])))
            price_m = PRICE_PATTERN.search(text)
            items[name_m.group(1)] = {
                "pid": name_m.group(1),
                "name": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", name_m.group(2)))).strip(),
                "list_price": int(price_m.group(1).replace(",", "")) if price_m else None,
                "sold_out": "SOLD OUT" in text.upper(),
            }
        if new == 0:
            break
        time.sleep(0.5)
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    html_text = fetch_html(f"{BASE_URL}/?pid={pid}")
    colorme_m = COLORME_PATTERN.search(html_text)
    product = json.loads(colorme_m.group(1)).get("product", {}) if colorme_m else {}

    # 最小重量・豆のままのバリエーション
    best = None
    for v in product.get("variants", []):
        w_m = re.search(r"(\d+)\s*g", unicodedata.normalize("NFKC", v.get("option2_value") or ""), re.I)
        if not w_m or "豆" not in (v.get("option1_value") or ""):
            continue
        weight = int(w_m.group(1))
        if best is None or weight < best[0]:
            best = (weight, v.get("option_price_including_tax"), v.get("stock_num"))

    desc_m = DESC_PATTERN.search(html_text)
    desc_raw = None
    if desc_m:
        desc_raw = re.sub(r"<br\s*/?>", "\n", desc_m.group(1))
        desc_raw = unicodedata.normalize("NFKC", re.sub(r"<[^>]+>", "", desc_raw)).replace("&nbsp;", " ").strip()
    return {
        "weight": best[0] if best else None,
        "price": best[1] if best else None,
        "variant_stock": best[2] if best else None,
        "product_stock": product.get("stock_num"),
        "description": desc_raw,
    }


def build_record(item: dict) -> dict | None:
    name = item["name"]
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return None
    detail = fetch_detail(item["pid"])
    if detail["weight"] is None:
        return None

    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            detected = detect_country_name(name)
            if detected:
                parsed["origin_country"] = detected
                parsed["origin_source"] = "raw_name"
        if not parsed["origin_country"]:
            for kw, country in ORIGIN_OVERRIDES.items():
                if kw in name:
                    parsed["origin_country"] = country
                    parsed["origin_source"] = "raw_name"
                    break
        parsed = apply_category_hint_fallback(parsed, name)

    desc = detail["description"]
    desc_oneline = re.sub(r"\s+", " ", desc).strip() if desc else None
    roast_m = (ROAST_LINE_PATTERN.search(desc) if desc else None) or ROAST_NAME_PATTERN.search(name)
    roast_hint = roast_m.group(1) if roast_m else None
    if roast_hint is None and desc_oneline:
        # 「煎り具合」欄の無い商品は、説明文中の焙煎度表記が1種類だけの場合に限り採用する
        mentioned = set(ROAST_NAME_PATTERN.findall(desc_oneline))
        if len(mentioned) == 1:
            roast_hint = mentioned.pop()

    sold_out = item["sold_out"] or detail["product_stock"] == 0 or detail["variant_stock"] == 0

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": roast_hint,
        "roast_selectable": False,
        "flavor_notes": (desc_oneline[:400] or None) if desc_oneline else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"] if detail["price"] is not None else None,
        "weight_g": detail["weight"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/?pid={item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if any(kw in item["name"] for kw in EXCLUDE_KEYWORDS):
            continue
        try:
            record = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={item['pid']} ({e})")
            continue
        if record is not None:
            records.append(record)
        time.sleep(0.5)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_mameyamato.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameyamato.json に出力しました")


if __name__ == "__main__":
    main()
