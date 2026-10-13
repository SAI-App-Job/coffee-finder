# -*- coding: utf-8 -*-
"""
scrape_akayacoffee.py

アカヤコーヒー(鹿児島県鹿児島市金生町7-13、公式 http://akayacoffee.com/、
カラーミーショップ http://akayacoffee.shop-pro.jp/)の自家焙煎コーヒー豆の
商品情報を取得する。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

robots.txt確認済み(2026-10): /secure/ と /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
全商品一覧(?mode=srh&cid=&keyword=、ページ送りあり)から取得する。
ドリップバッグ・ギフトセット・濾紙などの器具は除外する。

【価格・重量】
詳細ページの var Colorme の variants は「重量(100g/200g/500g/1kg)×挽き方」の組み合わせ。
最小重量(100g)の価格(税込)を代表に採用する。

【産地・焙煎度】
シングルオリジンの「生産地」「農園」「産地標高」「生産方法(精製)」、ブレンドの
「ブレンド配合」を説明文から取る。店頭ページに焙煎度の記載がない場合は None。
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
    "name": "アカヤコーヒー",
    "url": "http://akayacoffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "鹿児島県鹿児島市金生町7-13",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "http://akayacoffee.shop-pro.jp/"
LIST_URL = BASE_URL + "?mode=srh&cid=&keyword="
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["ドリップバッグ", "ギフト", "セット", "濾紙", "ろ紙", "フィルター", "ドリッパー"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g)", re.IGNORECASE)


def fetch_page(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup, text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def to_grams(s: str):
    m = WEIGHT_PATTERN.search(s or "")
    if not m:
        return None
    v = float(m.group(1))
    return int(v * 1000) if m.group(2).lower() == "kg" else int(v)


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 10):
        url = LIST_URL if page == 1 else f"{LIST_URL}&page={page}"
        soup, _ = fetch_page(url)
        units = soup.select("li.prd-lst-unit")
        if not units:
            break
        for u in units:
            a = u.select_one("span.prd-lst-name a")
            if not a:
                continue
            name = clean(a.get_text())
            href = a["href"]
            if any(k in name for k in NON_BEAN_KEYWORDS) or href in seen:
                continue
            seen.add(href)
            items.append({
                "url": BASE_URL + href.lstrip("/"),
                "list_name": name,
                "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫なし", u.get_text(" "))),
            })
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def parse_detail(item: dict) -> dict | None:
    soup, text = fetch_page(item["url"])
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        return None
    product = json.loads(m.group(1)).get("product")
    if not product:
        return None
    name = clean(product.get("name"))
    best = None
    for v in product.get("variants") or []:
        w = to_grams(v.get("option1_value"))
        price = v.get("option_price_including_tax")
        if w is None:
            continue
        if best is None or w < best[0] or (w == best[0] and price is not None and best[1] is not None and price < best[1]):
            best = (w, price)
    weight, price = best if best else (None, product.get("sales_price_including_tax"))

    exp = soup.select_one("div.product-order-exp")
    body = exp.get_text("\n") if exp else ""
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    # 味のチャート(酸味/甘み/コク/苦み/香り と数字)を除いた説明文
    chart_words = {"酸味", "甘み", "コク", "苦み", "香り"}
    desc_lines = [l for l in lines if l not in chart_words and not re.fullmatch(r"\d", l)]

    def after(label):
        for i, l in enumerate(lines):
            if l == label and i + 1 < len(lines):
                return lines[i + 1]
        return None

    blend_comp = []
    if "【ブレンド配合】" in body:
        seg = body.split("【ブレンド配合】", 1)[1].split("※")[0]
        for l in seg.split("\n"):
            l = l.strip().lstrip("・").strip()
            if l:
                blend_comp.append(clean(l))
    return {
        "name": name, "price": price, "weight": weight, "url": item["url"],
        "sold_out": item["sold_out"],
        "stock_num": product.get("stock_num"),
        "desc": desc_lines,
        "origin_label": after("生産地"), "farm": after("農園"), "elevation": after("産地標高"),
        "process": after("生産方法"), "grade_label": after("スクリーン/規格"),
        "blend_comp": blend_comp,
        "roast_text": next((l for l in desc_lines if re.search(r"(浅|中|深)煎り|ロースト|焙煎度", l)), None),
    }


def build_record(d: dict) -> dict | None:
    name = d["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    is_blend = "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if not parsed["origin_country"]:
            c = detect_country_name(name) or (detect_country_name(d["origin_label"]) if d["origin_label"] else None)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if d.get("process") and not parsed["processing_method"]:
            parsed["processing_method"] = normalize_processing_method(d["process"])
        parsed = apply_category_hint_fallback(parsed, name)
    farm_parts = []
    if d.get("origin_label"):
        farm_parts.append(f"生産地: {d['origin_label']}")
    if d.get("farm"):
        farm_parts.append(f"農園: {d['farm']}")
    if d.get("elevation"):
        farm_parts.append(f"標高: {d['elevation']}")
    out = d["sold_out"] or (isinstance(d.get("stock_num"), int) and d["stock_num"] <= 0)
    flavor = " ".join(
        l for l in d["desc"]
        if not l.startswith(("【ブレンド配合】", "・", "※", "生産地", "農園", "産地標高", "スクリーン", "生産方法"))
        and l not in (d.get("origin_label"), d.get("farm"), d.get("elevation"), d.get("process"), d.get("grade_label"))
    ) or None
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"] or d.get("grade_label"),
        "roast_level": parsed["roast_level"],
        "roast_hint": d.get("roast_text"),
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": flavor,
        "blend_components": d["blend_comp"] if is_blend else [],
        "decaf_process": None,
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": bool(out),
        "product_url": d["url"],
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in scrape_list():
        try:
            d = parse_detail(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['url']} ({e})")
            continue
        time.sleep(CRAWL_DELAY_SECONDS)
        if not d:
            continue
        rec = build_record(d)
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_akayacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_akayacoffee.json に出力しました")


if __name__ == "__main__":
    main()
