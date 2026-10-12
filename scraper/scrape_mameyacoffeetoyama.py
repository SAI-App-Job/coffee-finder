# -*- coding: utf-8 -*-
"""
scrape_mameyacoffeetoyama.py

まめやコーヒー(富山県富山市総曲輪、カラーミーショップ mameya-coffee.shop-pro.jp、
公式 https://mameya.coffee/)の自家焙煎コーヒー豆の商品情報を取得する。
(scrape_mameya.py は横浜の Mameya Roastery の別店舗のため、別名にしている)

robots.txt確認済み(2026-10): /secure/ と /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
全商品一覧(?mode=srh&cid=&keyword=、ページ送りあり)から取得する。一覧は
li.prd-lst-unit。セット・ドリップバッグ・ギフト・ギフト用ボックスは除外する。

【価格・重量】
詳細ページの var Colorme の variants(量: 200g/300g/400g/500g)の最小重量(200g)を
代表とし、option_price_including_tax(税込)を採用する。表示価格は「生豆200gを
煎ったお値段」で、焙煎後は180g前後になる旨が記載されているが、販売単位として200gとする。
店舗では100g小分けを休止中のため、ネットは200g〜のみ。

【焙煎度】
多くの商品は注文時にお好みの焙煎度を選べる(店のおすすめを「おすすめの焙煎度」として
保持)ため roast_level は None、roast_hint におすすめを入れる。ブレンド等
「…のみになります」と焙煎度が固定の商品は、その焙煎度を roast_level ではなく roast_hint
(固定)として保持する。
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
    "name": "まめやコーヒー",
    "url": "https://mameya-coffee.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "富山県富山市総曲輪3-2-21",
    "prefecture": "富山県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://mameya-coffee.shop-pro.jp/"
LIST_URL = "https://mameya-coffee.shop-pro.jp/?mode=srh&cid=&keyword="
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}
NON_BEAN_KEYWORDS = ["セット", "ドリップバッグ", "ギフト", "箱のみ"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)
FIXED_ROAST_PATTERN = re.compile(r"焙煎度合[いは]*(?:は)?[、\s]*(?:おすすめの)?[「]?([^「」\n]+?)[」]?(?:の)?のみ")
RECOMMEND_PATTERN = re.compile(
    r"((?:ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ロースト\([^)]*\))")
STOP_PATTERN = re.compile(r"^(★|●|■|◆|・)")
SKIP_PATTERN = re.compile(r"^(＊|※|\(※)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup, text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items = []
    page = 1
    while True:
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
            if any(k in name for k in NON_BEAN_KEYWORDS):
                continue
            text = u.get_text(" ")
            items.append({
                "url": BASE_URL + a["href"].lstrip("/"),
                "list_name": name,
                "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫なし", text)),
            })
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)
    return items


def parse_detail(item: dict) -> dict | None:
    soup, text = fetch_page(item["url"])
    m = COLORME_JSON_PATTERN.search(text)
    if not m:
        return None
    try:
        product = json.loads(m.group(1)).get("product")
    except json.JSONDecodeError:
        return None
    if not product:
        return None
    name = clean(product.get("name"))
    # 最小重量のバリエーション
    best = None
    for v in product.get("variants") or []:
        wm = WEIGHT_PATTERN.search(v.get("option1_value") or "")
        if not wm:
            continue
        w = int(wm.group(1))
        price = v.get("option_price_including_tax")
        if best is None or w < best[0]:
            best = (w, price)
    weight, price = best if best else (None, product.get("sales_price_including_tax"))

    exp = soup.select_one("div.product-order-exp")
    body = exp.get_text("\n") if exp else ""
    lines = [l.strip() for l in body.split("\n") if l.strip()]
    # テイスティング文: 先頭から「★」「●」等の注記行の前まで
    flavor = []
    for l in lines:
        if STOP_PATTERN.match(l):
            break
        if SKIP_PATTERN.match(l):
            continue
        flavor.append(l)
    flavor_notes = "".join(flavor) or None

    fixed = FIXED_ROAST_PATTERN.search(body)
    roast_hint = None
    if fixed:
        roast_hint = fixed.group(1).strip()
    else:
        star = body.split("★", 1)[1] if "★" in body else ""
        star = star.split("別の焙煎度合")[0].split("その他の焙煎度合")[0]
        rec = list(dict.fromkeys(RECOMMEND_PATTERN.findall(star)))
        if not rec:
            # 一覧の焙煎度合セレクト(オススメ印付き)から
            for v in product.get("variants") or []:
                o2 = v.get("option2_value") or ""
                if "オススメ" in o2:
                    mm = RECOMMEND_PATTERN.search(o2)
                    if mm and mm.group(1) not in rec:
                        rec.append(mm.group(1))
        if rec:
            roast_hint = "おすすめ: " + "/".join(rec)

    def label(key):
        mm = re.search(r"(?:" + key + r")\s*[：:]\s*([^\n]*)", body)
        return (mm.group(1).strip() or None) if mm else None

    return {
        "name": name, "price": price, "weight": weight, "url": item["url"],
        "sold_out": item["sold_out"], "flavor_notes": flavor_notes, "roast_hint": roast_hint,
        "origin_label": label(r"生産地|産地"), "process": label(r"精選|精製|プロセシング|カフェイン除去方法"),
        "farm": label(r"農園"), "variety": label(r"品\s*種"), "elevation": label(r"標\s*高"),
        "stock_num": product.get("stock_num"),
    }


def build_record(d: dict) -> dict:
    name = d["name"]
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return {"shop_name": SHOP_INFO["name"], "raw_name": name, "category": "フレーバー",
                "is_flavored": True, "flavor_name": parsed["flavor_name"],
                "price": d["price"], "product_url": d["url"]}
    if parsed["category"] != "ブレンド":
        if not parsed["origin_country"]:
            c = detect_country_name(name) or (detect_country_name(d["origin_label"]) if d["origin_label"] else None)
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        if d.get("process") and not parsed["processing_method"] and "スイス" not in d["process"]:
            parsed["processing_method"] = normalize_processing_method(d["process"])
    parsed = apply_category_hint_fallback(parsed, None)
    farm_parts = []
    if d.get("farm"):
        farm_parts.append(f"農園: {d['farm']}")
    if d.get("variety"):
        farm_parts.append(f"品種: {d['variety']}")
    decaf = None
    if "カフェインレス" in name or "デカフェ" in name:
        decaf = f"{d['process']}によりカフェインを除去" if d.get("process") else "デカフェ(除去方法の詳細記載なし)"
    out = d["sold_out"] or (isinstance(d.get("stock_num"), int) and d["stock_num"] <= 0)
    stock_status = "一時的に品切れ" if out else "販売中"
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
        "roast_hint": d.get("roast_hint"),
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": d.get("flavor_notes"),
        "blend_components": [],
        "decaf_process": decaf,
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": stock_status,
        "out_of_stock": out,
        "product_url": d["url"],
    }


def scrape_all_products():
    records, flavored = [], []
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
        (flavored if rec.get("is_flavored") else records).append(rec)
    return records, flavored


if __name__ == "__main__":
    records, flavored = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records, "flavored_products_excluded": flavored}
    with open("data_mameyacoffeetoyama.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_mameyacoffeetoyama.json に出力しました(フレーバー{len(flavored)}件は別枠)")
