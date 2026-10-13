# -*- coding: utf-8 -*-
"""
scrape_dinizcoffee.py

ジニス コーヒー&スイーツ(DINIZ、鹿児島県鹿児島市城山町2-30 石蔵、
オンラインショップ https://shop.diniz.co.jp/ )のスペシャルティコーヒー(自家焙煎豆)の
商品情報を取得する。カラーミーショップ(dinizcoffee.shop-pro.jp)。

【店舗発見の経緯】
全国再調査(鹿児島県)の新規発掘で発見。

robots.txt確認済み(2026-10): /secure/ と /cart/ のみ Disallow。

【文字コード】EUC-JP。

【商品の取得】
カテゴリ「スペシャルティコーヒー Specialty Coffee」(cbid=1619825)の一覧から取得する。
テイスティングセット・カップオンコーヒー・スイーツ・ギフトは除外し、
商品名に「200g」を含む豆の商品(シングルオリジン)だけを対象とする。

【価格・重量・産地・焙煎度】
価格は販売価格(税込、会員価格ではなく通常価格)。重量は「内容量: 200g/袋」(各商品1種類のみ)。
商品説明の「原産国」「品種」「焙煎度」の表記から産地・焙煎度・品種を取る。
(ソウル・メイトのページはメタ説明・英語見出しがルワンダの文面だが、商品名・原産国表記は
インドネシアのため、表の「原産国」に従う。)
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ジニス コーヒー&スイーツ",
    "url": "https://shop.diniz.co.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "鹿児島県鹿児島市城山町2-30 石蔵",
    "prefecture": "鹿児島県",
    "robots_txt_status": "許可(2026-10確認。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://shop.diniz.co.jp/"
CATEGORY_URL = BASE_URL + "?mode=cate&cbid=1619825&csid=0"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
NON_BEAN_KEYWORDS = ["セット", "カップオン", "ギフト", "ゼリー", "プリン", "ババロア", "スイーツ"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*?\});\s*\n", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g", re.IGNORECASE)


def fetch_page(url: str):
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode("euc-jp", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for br in soup.find_all("/br"):
        br.decompose()
    return soup, text


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("　", " ")).strip()


def scrape_list() -> list[dict]:
    items, seen = [], set()
    for page in range(1, 6):
        url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}&page={page}"
        soup, _ = fetch_page(url)
        found = 0
        for a in soup.find_all("a", href=re.compile(r"[?&]pid=\d+")):
            name = clean(a.get_text())
            m = re.search(r"pid=(\d+)", a["href"])
            if not name or not m or m.group(1) in seen:
                continue
            found += 1
            seen.add(m.group(1))
            if any(k in name for k in NON_BEAN_KEYWORDS) or not WEIGHT_PATTERN.search(name):
                continue
            items.append({"pid": m.group(1), "list_name": name,
                          "url": f"{BASE_URL}?pid={m.group(1)}"})
        time.sleep(CRAWL_DELAY_SECONDS)
        if not found:
            break
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
    variants = product.get("variants") or []
    prices = [v.get("option_price_including_tax") for v in variants if v.get("option_price_including_tax")]
    price = min(prices) if prices else product.get("sales_price_including_tax")

    exp = soup.select_one("div.product_explain")
    body = exp.get_text("\n") if exp else ""
    lines = [l.strip() for l in body.split("\n") if l.strip()]

    def label(key):
        for l in lines:
            mm = re.match(r"^" + key + r"\s*[：:]\s*(.+)$", l)
            if mm:
                return mm.group(1).strip()
        return None

    weight = None
    wl = label("内容量")
    if wl and WEIGHT_PATTERN.search(wl):
        weight = int(WEIGHT_PATTERN.search(wl).group(1))
    elif WEIGHT_PATTERN.search(name):
        weight = int(WEIGHT_PATTERN.search(name).group(1))

    def section(title):
        for i, l in enumerate(lines):
            if l == title and i + 1 < len(lines):
                return lines[i + 1]
        return None

    return {
        "name": name, "price": price, "weight": weight, "url": item["url"],
        "origin_label": label("原産国"), "variety": label("品種"), "roast_label": label("焙煎度"),
        "message": section("Coffee Message"),
        "flavor": section("風味のプロファイル"),
        "terroir": section("生産地について"),
        "sold_out": bool(re.search(r"売り切れ|SOLD ?OUT|在庫切れ", clean(soup.select_one("div.add_cart").get_text()) if soup.select_one("div.add_cart") else "")),
        "stock_num": product.get("stock_num"),
    }


def build_record(d: dict) -> dict | None:
    # 商品名「エチオピア『エキサイティング・ジャーニー』200g」→ 重量表記を除く
    name = clean(re.sub(r"\s*\d+\s*g\s*$", "", d["name"], flags=re.IGNORECASE))
    parsed = parse_product(name)
    if parsed["is_flavored"]:
        return None
    parsed["category"] = "ストレート"
    country = detect_country_name(d["origin_label"]) if d["origin_label"] else None
    if country:
        parsed["origin_country"] = country
        parsed["origin_source"] = "product_description"
    elif not parsed["origin_country"]:
        c = detect_country_name(name)
        if c:
            parsed["origin_country"] = c
            parsed["origin_source"] = "raw_name"
    parsed = apply_category_hint_fallback(parsed, name)
    roast_level = None
    if d["roast_label"] and "ライトシティ" not in d["roast_label"]:
        # 「ライトシティロースト」は標準の8段階に無い表記のため roast_level は None にして
        # roast_hint(原文)だけ保持する
        roast_level = parse_product(d["roast_label"])["roast_level"]
    farm_parts = []
    if d.get("variety"):
        farm_parts.append(f"品種: {d['variety']}")
    out = bool(d["sold_out"]) or (isinstance(d.get("stock_num"), int) and d["stock_num"] <= 0)
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "roast_hint": d["roast_label"],
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": " / ".join(farm_parts) or None,
        "flavor_notes": d["flavor"],
        "blend_components": [],
        "decaf_process": None,
        "price": d["price"],
        "weight_g": d["weight"],
        "stock_status": "一時的に品切れ" if out else "販売中",
        "out_of_stock": out,
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
    with open("data_dinizcoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_dinizcoffee.json に出力しました")


if __name__ == "__main__":
    main()
