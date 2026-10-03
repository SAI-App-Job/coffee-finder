# -*- coding: utf-8 -*-
"""
scrape_sanimu.py

自家焙煎珈琲豆サニム(sanimu.chashinan.com、神奈川県横須賀市久里浜4-14-1。ご注文を受けてから
焙煎するコーヒー豆店)の商品情報を取得する。EC-CUBE系のオンラインショップ。
商品一覧(`products/list.php?category_id=0&disp_number=50`)の全32件を対象に、各商品詳細ページ
(`products/detail.php?product_id=N`)の規格(豆の状態・焙煎度合)ごとの在庫情報で在庫を判定する。

【店舗発見の経緯】
全国再調査(神奈川県)で発掘。トップに2026年10月4日付の新着情報(ハロウィンブレンド)があり現行。

【対象商品について】
実データ確認済み(2026-10時点): 32件すべてコーヒー豆(ストレート・ブレンド)。ドリップバッグ・
器具の掲載はない。内容量は商品名末尾の「200g」「500g」(黒船ブレンド2種のみ500g)で、
サイト記載のとおり「ご注文時のグラム数は生豆時のグラム数」(焙煎後は15~20%目減り)。
価格はその税込販売価格で、商品ごとに1サイズのみのため代表重量=名称表記のグラム数。
焙煎度はご注文時に選択する方式で、商品説明の「おすすめ焙煎度」をroast_hintに保持する
(roast_levelはNone)。商品名に産地がなくブレンド表記もない「アイスコーヒー」と、
「ふかふか」「コクまろ」「さらさら」はサイト上ブレンド扱いのためブレンドとする。
商品名の産地表記がない「カレンゲラ カブガ CWS」は説明文の「ルワンダ」から産地を取る。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "自家焙煎珈琲豆サニム",
    "url": "https://sanimu.chashinan.com/",
    "platform": "EC-CUBE",
    "address": "神奈川県横須賀市久里浜4-14-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://sanimu.chashinan.com/shop"
LIST_URL = f"{BASE_URL}/products/list.php?category_id=0&pageno=1&disp_number=50"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 0.3

WEIGHT_PATTERN = re.compile(r"\s*(\d+)\s*[gｇ]\s*$")
ROAST_PATTERN = re.compile(r"おすすめ焙煎(?:度)?[、,]\s*(.+)")
CLASS_CATEGORIES_PATTERN = re.compile(r"classCategories = (\{.*?\});function", re.S)


def get_text(url: str) -> str:
    last_err = None
    for _ in range(4):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as e:  # 一時的な名前解決エラー等に備えて再試行
            last_err = e
            time.sleep(2)
    raise last_err


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for d in soup.select("div.list_area"):
        a = d.select_one("a.productName")
        price_el = d.select_one("span[id^=price02_default]")
        if not a or not price_el:
            continue
        pid = re.search(r"product_id=(\d+)", a["href"]).group(1)
        comment = d.select_one("p.listcomment")
        comment_lines = [ln.strip() for ln in comment.get_text("\n").split("\n")] if comment else []
        items.append({
            "id": pid,
            "title": re.sub(r"\s+", " ", a.get_text(" ", strip=True)),
            "price": int(price_el.get_text(strip=True).replace(",", "")),
            "comment": [ln for ln in comment_lines if ln],
        })
    return items


def stock_and_category(pid: str) -> tuple[bool, bool]:
    """(在庫あり, サイト上のブレンドカテゴリ所属) を詳細ページから返す。"""
    html = get_text(f"{BASE_URL}/products/detail.php?product_id={pid}")
    m = CLASS_CATEGORIES_PATTERN.search(html)
    in_stock = True
    if m:
        data = json.loads(m.group(1))
        flags = [v.get("stock_find") for sub in data.values() for key, v in sub.items() if key != "#" and isinstance(v, dict) and "stock_find" in v]
        if flags:
            in_stock = any(flags)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    in_blend_cat = bool(re.search(r">\s*ブレンドコーヒー", text.replace("\n", " ")))
    return in_stock, in_blend_cat


def build_record(item: dict, in_stock: bool, in_blend_cat: bool) -> dict:
    title = item["title"]
    wm = WEIGHT_PATTERN.search(title)
    weight_g = int(wm.group(1)) if wm else None
    name = WEIGHT_PATTERN.sub("", title).strip()

    roast_hint = None
    desc_lines = []
    for ln in item["comment"]:
        rm = ROAST_PATTERN.match(ln)
        if rm and roast_hint is None:
            roast_hint = rm.group(1).strip()
            continue
        if ln.startswith("5段階評価"):
            break
        desc_lines.append(ln)
    desc = re.sub(r"\s+", " ", " ".join(desc_lines)).strip() or None

    parsed = parse_product(name)
    country = detect_country_name(name)
    name_has_origin = bool(country or parsed["origin_country"])
    if not name_has_origin and desc:
        # 商品名に産地が無い場合は説明文冒頭の産地表記から取る(例: カレンゲラ カブガ CWS → ルワンダ)
        country = detect_country_name(desc[:80])
    # ブレンド表記・サイト上のブレンドカテゴリ、または産地を特定できない商品(アイスコーヒー)はブレンド
    is_blend = "ブレンド" in name or in_blend_cat or not (country or parsed["origin_country"])
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        if country and not parsed["origin_country"]:
            parsed["origin_country"] = country
            parsed["origin_source"] = "raw_name" if detect_country_name(name) else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 焙煎度はご注文時に選択する方式
        "roast_hint": roast_hint,
        "flavor_notes": desc,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "販売中" if in_stock else "完売",
        "out_of_stock": not in_stock,
        "product_url": f"{BASE_URL}/products/detail.php?product_id={item['id']}",
    }


def scrape_all_products() -> list[dict]:
    items = parse_list(get_text(LIST_URL))
    records = []
    for item in items:
        try:
            in_stock, in_blend_cat = stock_and_category(item["id"])
        except requests.RequestException as e:
            print(f"[warn] 商品ページ取得失敗: {item['id']} ({e})")
            continue
        records.append(build_record(item, in_stock, in_blend_cat))
        time.sleep(REQUEST_INTERVAL)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_sanimu.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sanimu.json に出力しました")


if __name__ == "__main__":
    main()
