# -*- coding: utf-8 -*-
"""
scrape_oniyanma.py

ONIYANMA COFFEE(オニヤンマコーヒー、札幌市の自家焙煎スペシャルティコーヒー店)の
オンラインショップ(oniyanmacoffee.jp/store/)の商品情報を取得する。EC-CUBE 4。

【住所について】
依頼で指定された本店住所(北海道札幌市中央区南1条西6丁目21-1 センチュリーヒルズ1F、
「ONIYANMA COFFEE & BEER」)を採用した。なお公式トップ(oniyanmacoffee.jp)には札幌市内2拠点が
掲載されている(実データ確認済み、2026-10時点): 「ONIYANMA BASE」北海道札幌市東区北33条東
16丁目2-21 SAPPORO EAST3316 1F、「ONIYANMA COFFEE & BEER」と「ONIYANMA URA」が中央区
南1条西6丁目21-1 センチュリーヒルズ。ECサイトの「当サイトについて」の住所は前者(東区、
(株)ファインドリームス)である。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ブレンド」(category_id=11)・「シングル
オリジン」(12)・「デカフェ」(13)のコーヒー豆(計8商品。ページネーション無し)。
ドリップバッグ(ブレンド・デカフェ両カテゴリに各1件)とギフトセットは除外する。
全商品が「100g」単位の1バリエーションで、価格は税込表示(商品詳細に「税込」と明記)。
商品名末尾の「(中浅煎り)100g」から焙煎度と重量を取得する。
「Colombia - El Diviso Blend」は商品名に「Blend」を含むがサイト上はシングルオリジン
カテゴリのため、サイトのカテゴリに従いストレートとする。
在庫は一覧・詳細の「カートに入れる」ボタンの有無で判定する(品切れ時はボタンが
無くなるEC-CUBEの標準挙動)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method,
)

SHOP_INFO = {
    "name": "ONIYANMA COFFEE",
    "url": "https://oniyanmacoffee.jp/store/",
    "platform": "EC-CUBE",
    "address": "北海道札幌市中央区南1条西6丁目21-1 センチュリーヒルズ1F",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-10確認。User-agent: *にDisallow: /*.csv$のみ)",
}

BASE_URL = "https://oniyanmacoffee.jp/store"
CATEGORIES = [("11", "blend"), ("12", "single"), ("13", "single")]
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_WORDS = ("ドリップバッグ", "ギフト", "セット")
ROAST_PATTERN = re.compile(r"[(（]\s*(浅煎り|中浅煎り|中煎り|中深煎り|深煎り)\s*[)）]")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*g\s*$", re.I)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        soup = BeautifulSoup(fetch_html(f"{BASE_URL}/products/list?category_id={cat_id}"), "html.parser")
        for li in soup.select("li.ec-shelfGrid__item"):
            a = li.select_one("a[href*='/products/detail/']")
            if not a:
                continue
            pid = a["href"].rsplit("/", 1)[-1]
            if pid in items:
                continue
            name = ""
            for p in li.select("p"):
                if not p.get("class"):
                    name = p.get_text(" ", strip=True)
                    break
            price_el = li.select_one("p.price02-default, .price02-default")
            pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
            items[pid] = {
                "pid": pid,
                "name": name,
                "price": int(pm.group(1).replace(",", "")) if pm else None,
                "in_cart": li.select_one("button.add-cart") is not None,
                "group": group,
            }
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    soup = BeautifulSoup(fetch_html(f"{BASE_URL}/products/detail/{pid}"), "html.parser")
    desc_el = soup.select_one(".ec-productRole__description")
    desc = desc_el.get_text("\n", strip=True) if desc_el else ""
    return {
        "description": desc,
        "in_cart": soup.select_one("button.add-cart") is not None,
    }


def clean_name(name: str) -> tuple[str, str | None, int | None]:
    """商品名から末尾の重量と焙煎度(括弧書き)を分離する。(名称, 焙煎度, 重量g)。"""
    n = unicodedata.normalize("NFKC", name)
    n = re.sub(r"\s+", " ", n).strip()
    weight = None
    m = WEIGHT_PATTERN.search(n)
    if m:
        weight = int(m.group(1))
        n = n[:m.start()].strip()
    roast = None
    m = ROAST_PATTERN.search(n)
    if m:
        roast = m.group(1)
        n = (n[:m.start()] + " " + n[m.end():]).strip()
    return n, roast, weight


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if not item["name"] or item["price"] is None:
            continue
        if any(w in item["name"] for w in EXCLUDE_WORDS):
            continue
        name, roast, weight = clean_name(item["name"])
        detail = fetch_detail(item["pid"])
        desc = detail["description"]

        parsed = parse_product(name)
        is_blend = item["group"] == "blend"
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(name)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        if not parsed["processing_method"] and not is_blend:
            m = re.search(r"生産処理\s*[:：]\s*([^\n]+)", desc)
            if m:
                parsed["processing_method"] = detect_processing_method(m.group(1))

        farm = re.search(r"農園\s*[:：]\s*([^\n]+)", desc)
        # 説明文の保存方法・配送案内は除いて冒頭400字を採用
        desc_main = re.split(r"【保存方法】|【配送について】", desc)[0]
        flavor_notes = re.sub(r"\s+", " ", desc_main)[:400] or None

        available = item["in_cart"] and detail["in_cart"]
        status = "販売中" if available else "完売"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": name,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast,
            "roast_hint": roast,
            "flavor_notes": flavor_notes,
            "farm_note": farm.group(1).strip() if farm else None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": status,
            "out_of_stock": status != "販売中",
            "product_url": f"{BASE_URL}/products/detail/{item['pid']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_oniyanma.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_oniyanma.json に出力しました")


if __name__ == "__main__":
    main()
