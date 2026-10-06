# -*- coding: utf-8 -*-
"""
scrape_kayalamp.py

珈屋Lamp(Lamp焙煎工房、北海道旭川市末広東1条1丁目7-6の自家焙煎珈琲店)の商品情報を取得する。
FC2ショッピングカート(hotarufarm.cart.fc2.com。運営は自然耕房ホタルファーム)。

【住所について】
公式サイト(kaoricoffee.web.fc2.com/new1.html)で実データ確認済み(2026-10時点): 「珈屋Lamp
〒071-8121 北海道旭川市末広東1条1丁目7-6(代表 米脇)」。カートの特定商取引法ページの
所在地は農産加工元の「自然耕房ホタルファーム(上川郡当麻町東1区)」のため、店舗の住所は
公式サイト記載のものを採用する。

【対象商品について】
実データ確認済み(2026-10時点): 全36商品のうちカテゴリ「特注焙煎コーヒー豆」(ca=1、22商品、
1ページ10件の一覧を par_page=100 で全件取得)のみが対象。紅茶・健康茶・調味料・農産加工品・
健康食品は対象外。完全注文焙煎の豆で、同一銘柄が「200g/300g」(一部は250g・450gの
単独)の別商品として並ぶため、銘柄ごとに最小重量の商品を代表とする(重量違いは別商品名の
末尾の重量表記を除いた名称で同一銘柄と判定)。「無農薬ブラジル CR/FCR/FR」は焙煎度違いの
別商品のため別銘柄として扱う。
在庫は詳細ページの「再入荷お知らせ希望」フォームの有無で判定する(品切れ商品のみ表示)。
焙煎度は商品説明の「焙煎は標準的なシティ・ロースト」等の記述から取得する。説明の無い商品は null。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "珈屋Lamp",
    "url": "http://kaoricoffee.web.fc2.com/",
    "platform": "FC2ショッピングカート(cart.fc2.com)",
    "address": "北海道旭川市末広東1条1丁目7-6",
    "prefecture": "北海道",
    "robots_txt_status": "実質許可(2026-10確認。カート側robots.txtは/cancel/・/setup/・/tools/のみDisallow)",
}

BASE_URL = "http://hotarufarm.cart.fc2.com"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
MAX_PAGES = 6
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|g)", re.I)
ROAST_PATTERN = re.compile(r"焙煎は[^。]*?(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)・?ロースト")
ROAST_NAMES = {
    "ライト": "ライトロースト", "シナモン": "シナモンロースト", "ミディアム": "ミディアムロースト",
    "ハイ": "ハイロースト", "フルシティ": "フルシティロースト", "シティ": "シティロースト",
    "フレンチ": "フレンチロースト", "イタリアン": "イタリアンロースト",
}


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for page in range(0, MAX_PAGES):
        url = f"{BASE_URL}/?ca=1&par_page=100" + (f"&page={page}" if page else "")
        soup = BeautifulSoup(fetch_html(url), "html.parser")
        new = 0
        for li in soup.select("li.item_inner"):
            a = li.select_one("dt.name a")
            if not a:
                continue
            m = re.match(r"/ca1/(\d+)/", a["href"])
            if not m or m.group(1) in items:
                continue
            new += 1
            price_el = li.select_one("div.price")
            pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
            items[m.group(1)] = {
                "pid": m.group(1),
                "href": a["href"],
                "name": a.get_text(strip=True),
                "price": int(pm.group(1).replace(",", "")) if pm else None,
            }
        if new == 0:
            break
    return list(items.values())


def split_name(name: str) -> dict | None:
    """商品名から重量(200g・250g・450g等)を分離する。"""
    n = unicodedata.normalize("NFKC", name)
    m = WEIGHT_PATTERN.search(n)
    if not m:
        return None
    weight = int(m.group(1)) * (1000 if m.group(2).lower() == "kg" else 1)
    base = (n[:m.start()] + n[m.end():]).strip()
    base = re.sub(r"\s+", " ", base)
    return {"base": base, "weight": weight, "key": base.replace(" ", "")}


def fetch_detail(href: str) -> dict:
    html = fetch_html(BASE_URL + href)
    soup = BeautifulSoup(html, "html.parser")
    # .item_commentは価格・数量選択フォームまで含むため、説明文の.comment1/.comment2のみ使う
    parts = [e.get_text("\n", strip=True) for e in soup.select(".item_comment .comment1, .item_comment .comment2")]
    desc = "\n".join(t for t in parts if t) or None
    return {
        "description": desc,
        "sold_out": "再入荷お知らせ" in html,
    }


def scrape_all_products() -> list[dict]:
    best: dict[str, tuple[int, dict, dict]] = {}
    for item in list_items():
        parts = split_name(item["name"])
        if not parts or item["price"] is None:
            continue
        cand = (parts["weight"], item, parts)
        cur = best.get(parts["key"])
        if cur is None or cand[0] < cur[0]:
            best[parts["key"]] = cand

    records = []
    for weight, item, parts in best.values():
        base = parts["base"]
        detail = fetch_detail(item["href"])
        desc_full = detail["description"]
        desc = re.sub(r"\s+", " ", desc_full)[:400] if desc_full else None

        parsed = parse_product(base)
        if "ブレンド" in base:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
            parsed["designated_brand"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(base)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, base)

        roast_level = None
        if desc_full:
            m = ROAST_PATTERN.search(desc_full)
            if m:
                roast_level = ROAST_NAMES[m.group(1)]

        status = "完売" if detail["sold_out"] else "販売中"
        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "grade": parsed["grade"],
            "roast_level": roast_level,
            "roast_hint": roast_level,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": status,
            "out_of_stock": status != "販売中",
            "product_url": f"{BASE_URL}{item['href']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_kayalamp.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kayalamp.json に出力しました")


if __name__ == "__main__":
    main()
