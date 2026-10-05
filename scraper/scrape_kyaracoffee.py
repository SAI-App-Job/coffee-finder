# -*- coding: utf-8 -*-
"""
scrape_kyaracoffee.py

茶房・伽羅(きゃら)(www.coffee-kyara.com、愛知県名古屋市西区大野木4丁目20)の商品情報を取得する。
ショップサーブ(商品URLは/SHOP/<商品コード>.html、一覧は/SHOP/<カテゴリID>/list.html)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ストレートコーヒー」(25266、7件: S001/S003/S004/S005/
S006/S008/S010)と「ブレンドコーヒー」(28985、9件: B001〜B009)の計16件が全て200gの焙煎豆。
list2.html以降は空(ページネーションなし)。ドリップバッグ・ギフト・器具等は存在しない。
(S002/S007/S009は欠番)

【焙煎度について】
焙煎度は注文時に5段階(1浅煎り〜5深煎り)から顧客が選ぶ方式で、商品固有の固定値は無い
(roast_selectable=True、roast_level=None)。説明末尾の「おすすめ焙煎度合」で丸数字(①〜⑤)に
なっている段階を店推奨としてroast_hintに記録する。

【在庫について】
購入フォーム(form.shopping_form内の「購入数」入力)がある商品を販売中とする。全16件で購入可能。
(品切れ表示の例は確認できなかった)
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "茶房・伽羅",
    "url": "https://www.coffee-kyara.com/",
    "platform": "ショップサーブ",
    "address": "愛知県名古屋市西区大野木4丁目20",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(ショップサーブ標準構成)",
}

BASE_URL = "https://www.coffee-kyara.com"
CATEGORIES = [("25266", "single"), ("28985", "blend")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 6

TITLE_PATTERN = re.compile(r"^(.+?)\s*[(（][^)）]*コーヒー[)）]\s*(\d+)\s*g\s*$", re.I)
ROAST_STEPS = {"①": "浅煎り", "②": "やや浅煎り", "③": "中煎り", "④": "やや深煎り", "⑤": "深煎り"}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[tuple[str, str]]:
    items: dict[str, str] = {}
    for cat_id, group in CATEGORIES:
        for page in range(1, MAX_PAGES + 1):
            name = "list.html" if page == 1 else f"list{page}.html"
            resp = requests.get(f"{BASE_URL}/SHOP/{cat_id}/{name}", headers=REQUEST_HEADERS, timeout=30)
            if resp.status_code != 200:
                break
            resp.encoding = "utf-8"
            found = [c for c in dict.fromkeys(re.findall(r"/SHOP/([A-Z]\d+)\.html", resp.text)) if c not in items]
            if not found:
                break
            for c in found:
                items[c] = group
    return list(items.items())


def build_record(code: str, group: str) -> dict | None:
    html_text = fetch_html(f"{BASE_URL}/SHOP/{code}.html")
    soup = BeautifulSoup(html_text, "html.parser")
    title_el = soup.select_one("h2.title1.no2")
    if not title_el:
        return None
    raw = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", title_el.get_text(" ", strip=True)))
    tm = TITLE_PATTERN.match(raw)
    if not tm:
        return None
    title = tm.group(1).strip()
    weight_g = int(tm.group(2))

    for sc in soup(["script", "style"]):
        sc.decompose()
    text = soup.get_text("\n", strip=True)

    # 説明文: 商品見出し(h2)の直後〜「拡大表示」の手前
    desc = None
    m = re.search(r"\n" + re.escape(title_el.get_text(strip=True)) + r"\n(.*?)\n拡大表示", text, re.S)
    if m:
        desc = re.sub(r"\s+", " ", m.group(1)).strip()[:400] or None

    price_el = soup.select_one(".price")
    pm = re.search(r"([\d,]+)\s*円", price_el.get_text()) if price_el else None
    price = int(pm.group(1).replace(",", "")) if pm else None

    in_stock = "購入数" in text

    hint = None
    hm = re.search(r"おすすめ焙煎度合】\s*([^【]*)", text)
    if hm:
        for ch, label in ROAST_STEPS.items():
            if ch in hm.group(1):
                hint = f"おすすめ焙煎度合: {label}"
                break

    parsed = parse_product(title)
    if group == "blend":
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
        parsed["designated_brand"] = None
    else:
        parsed["category"] = "ストレート"
        if not parsed["origin_country"]:
            c = detect_country_name(desc or "")
            if c:
                parsed["origin_country"] = c
                parsed["origin_source"] = "product_description"
        parsed = apply_category_hint_fallback(parsed, title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,
        "roast_hint": hint,
        "roast_selectable": True,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE_URL}/SHOP/{code}.html",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for code, group in list_items():
        try:
            rec = build_record(code, group)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {code} ({e})")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kyaracoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kyaracoffee.json に出力しました")


if __name__ == "__main__":
    main()
