# -*- coding: utf-8 -*-
"""
scrape_blendia.py

Blendia(ブレンディア、tigers0031.ocnk.net、神奈川県横浜市青葉区あざみ野2-28-1 パールビルA102、
販売主 長谷川力、注文を受けて焙煎度を選んで焙煎する自家焙煎コーヒー店)の商品情報を取得する。
おちゃのこネット(UTF-8)。

【自家焙煎・住所の確認(2026-10)】
特定商取引法ページの所在地は神奈川県横浜市青葉区あざみ野2-28-1 パールビルA102(販売主 長谷川力)。
トップのキーワードに「自家焙煎・選べる焙煎度合い」、各商品ページに焙煎度合い7段階(シナモン〜
イタリアン)の選択肢と「豆袋の表示は焙煎前の生豆量です(焙煎で15〜20%目減り)」とあり、注文焙煎を確認。
お知らせの最新は2026-10-02で現行運営。単独店舗。
(自家焙煎である旨の明文は、サイトのキーワードと焙煎度合いの選択・目減りの説明による。)

【対象商品について】
実データ確認済み(2026-10時点): 「全商品」(/product-list、1ページ34件)から、ドリップバッグ(1件)を除く
33件を巡回する。商品は「重量」オプション(100g/200g/300g/400g/500g、季節ブレンドは200gから)と「焙煎」
オプション(7段階)を持つバリエーション商品で、詳細ページのJS(pConf.priceArray)から最小サイズの
価格を読み取り、最小サイズ(100g、季節ブレンドは200g)を代表値とする。焙煎度は注文者が選ぶため
roast_levelは持たず、roast_hintに「注文時に7段階から選択」と記す。
同じ商品名が複数ページに重複登録されているもの(季節のブレンド「秋」、ケニア アダロニア AA、
パプアニューギニア コセム ティピカ ブラックハニー、侍ブレンド カフェインレス、
ブラジル キャラメラード カフェインレス)は、在庫ありを優先し1件に統合する。
在庫は詳細ページに「カートに入れる」が無ければ完売とする。
原産国・品種・精製は説明冒頭の「原産国/ベトナム　品種/カティモール　精製/ウォッシュド」から読む。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
)

SHOP_INFO = {
    "name": "Blendia",
    "url": "https://tigers0031.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "神奈川県横浜市青葉区あざみ野2-28-1 パールビルA102",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://tigers0031.ocnk.net"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
LIST_URL = f"{BASE_URL}/product-list"
EXCLUDE_KEYWORDS = ("ドリップバッグ", "セット", "ギフト")
ORIGIN_OVERRIDES = {"タイ ": "タイ"}
ROAST_HINT = "注文時に焙煎度(シナモン〜イタリアンの7段階)を選択"

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
UNIT_OPTION_PATTERN = re.compile(r'<option value="(\d+)">\s*(\d+)\s*g\s*</option>')
SPEC_PATTERN = re.compile(r"(原産国|品種|精製)/\s*([^\s　]+(?:[・、][^\s　]+)*)")


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")
    items, seen = [], set()
    for card in soup.select("li.list_item_cell"):
        a = card.select_one("a[href*='/product/']")
        pid_m = re.search(r"/product/(\d+)", a.get("href", "")) if a else None
        if not pid_m or pid_m.group(1) in seen:
            continue
        seen.add(pid_m.group(1))
        items.append({
            "pid": pid_m.group(1),
            "title": unicodedata.normalize("NFKC", re.sub(r"\s+", " ", card.select_one(".goods_name").get_text(strip=True))).strip(),
        })
    return items


def fetch_detail(pid: str) -> dict:
    html_text = fetch(f"{BASE_URL}/product/{pid}")
    units = [(int(w), uid) for uid, w in UNIT_OPTION_PATTERN.findall(html_text)]
    weight_g, price = None, None
    if units:
        weight_g, uid = min(units)
        pm = re.search(rf"priceArray\[1\]\[{uid}\](?:\[\d+\])?\s*=\s*(\d+)", html_text)
        price = int(pm.group(1)) if pm else None
    soup = BeautifulSoup(html_text, "html.parser")
    if price is None:
        sp = soup.select_one(".selling_price")
        pm = PRICE_PATTERN.search(sp.get_text(" ", strip=True)) if sp else None
        price = int(pm.group(1).replace(",", "")) if pm else None
    text = unicodedata.normalize("NFKC", soup.get_text("\n", strip=True))
    i = text.find("商品詳細")
    head = text[:i] if i >= 0 else text
    body_end = text.find("焙煎と挽き方の目安", i if i >= 0 else 0)
    body = text[i + len("商品詳細"):body_end] if i >= 0 and body_end > i else ""
    specs = dict(SPEC_PATTERN.findall(body.replace("\n", " ")))
    story = [ln for ln in body.split("\n") if ln.strip() and not SPEC_PATTERN.search(ln) and ln.strip() != "商品詳細"]
    return {
        "weight_g": weight_g,
        "price": price,
        "in_stock": "カートに入れる" in head,
        "specs": specs,
        "story": " ".join(story),
    }


def build_record(item: dict, detail: dict) -> dict:
    name = item["title"]
    parsed = parse_product(name)
    specs = detail["specs"]
    if parsed["category"] == "ブレンド":
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        processing = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if name.startswith(k)), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name"
        parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["origin_country"] and specs.get("原産国"):
            c = detect_country_name(specs["原産国"])
            if c:
                parsed["origin_country"], parsed["origin_source"] = c, "country_name"
        processing = parsed["processing_method"]
        if not processing and specs.get("精製"):
            processing = normalize_processing_method(specs["精製"])
    farm_bits = [f"{k}: {specs[k]}" for k in ("品種",) if specs.get(k)]
    sold_out = not detail["in_stock"]
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing,
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": ROAST_HINT,
        "flavor_notes": detail["story"][:300] or None,
        "farm_note": "、".join(farm_bits) if farm_bits else None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": detail["price"],
        "weight_g": detail["weight_g"],
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": f"{BASE_URL}/product/{item['pid']}",
    }


def scrape_all_products() -> list[dict]:
    by_name: dict[str, dict] = {}
    for it in list_items():
        if any(k in it["title"] for k in EXCLUDE_KEYWORDS):
            continue
        try:
            detail = fetch_detail(it["pid"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: pid={it['pid']} ({e})")
            continue
        rec = build_record(it, detail)
        key = rec["raw_name"]
        prev = by_name.get(key)
        # 同名の重複登録は在庫ありを優先し、同条件なら先に出たものを残す
        if prev is None or (prev["out_of_stock"] and not rec["out_of_stock"]):
            by_name[key] = rec
        time.sleep(0.3)
    return list(by_name.values())


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_blendia.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_blendia.json に出力しました")


if __name__ == "__main__":
    main()
