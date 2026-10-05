# -*- coding: utf-8 -*-
"""
scrape_shimizucoffee.py

清水珈琲(shimizucoffee.ocnk.net、愛知県名古屋市北区大曽根2-3-5 サン大曽根1F)の
商品情報を取得する。おちゃのこネット(Ocnk、旧式テーマ)。

【対象商品について】
実データ確認済み(2026-10時点): カテゴリ「ブレンド」(product-list/1、8件)と「ストレート」
(product-list/2、16件)のコーヒー豆24件(12銘柄×200g/500gの別商品)を、銘柄ごとに最小重量の
200g商品を代表として採用する。「カフェオレベース」(product-list/4)は飲料のため対象外。
「特別商品」(product-list/3)は登録0件。

【ページ構造について】
旧式テーマのため一覧は`table.list_item_table`(h2 a=商品名・リンク、.pricech=価格)。
重量は商品名末尾「(200g)」。商品ページ内の`div.detail_desc_box`が説明文で、
「生産国 〇〇」「精製方法 〇〇」等が空白区切りで書かれている(銘柄による)。
焙煎度は、サイドメニュー「煎り具合」の絞り込み(product-group/1=深煎り、2=中深煎り、3=中煎り)
に掲載されている銘柄の分類をそのまま採用する。
在庫は購入ボタン(input.cartaddinput)の有無で判定する(現状は全件あり)。

【サイトの鮮度について(2026-10時点)】
お知らせの最新は2025-12-01(年末年始の営業時間)で、フッターの著作権表示は2009-2020。
価格・在庫が現行かは確認できない(ページ自体は購入可能な状態)。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product, apply_category_hint_fallback, detect_country_name, normalize_processing_method,
)

SHOP_INFO = {
    "name": "清水珈琲",
    "url": "https://shimizucoffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "愛知県名古屋市北区大曽根2-3-5 サン大曽根1F",
    "prefecture": "愛知県",
    "robots_txt_status": "未確認(Ocnk標準構成)",
}

BASE_URL = "https://shimizucoffee.ocnk.net"
CATEGORIES = [("1", "blend"), ("2", "single")]
ROAST_GROUPS = {"1": "深煎り", "2": "中深煎り", "3": "中煎り"}  # product-group/<id>
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}

NAME_PATTERN = re.compile(r"^(.+?)\s*[(（]\s*(\d+(?:\.\d+)?)\s*(kg|g)\s*[)）]\s*$", re.I)


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_table_items(html_text: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for tb in soup.select("table.list_item_table"):
        a = tb.select_one("h2 a")
        if not a:
            continue
        m = re.search(r"/product/(\d+)", a["href"])
        if not m:
            continue
        price_el = tb.select_one(".pricech")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        out.append({
            "pid": m.group(1),
            "name": re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip(),
            "price": int(pm.group(1).replace(",", "")) if pm else None,
        })
    return out


def list_items() -> list[dict]:
    items: dict[str, dict] = {}
    for cat_id, group in CATEGORIES:
        for page in range(1, 6):
            url = f"{BASE_URL}/product-list/{cat_id}" + ("" if page == 1 else f"/0/photo?page={page}")
            new = 0
            for it in list_table_items(fetch_html(url)):
                if it["pid"] not in items:
                    it["group"] = group
                    items[it["pid"]] = it
                    new += 1
            if new == 0:
                break
    return list(items.values())


def roast_by_pid() -> dict[str, str]:
    result: dict[str, str] = {}
    for gid, roast in ROAST_GROUPS.items():
        for it in list_table_items(fetch_html(f"{BASE_URL}/product-group/{gid}")):
            result[it["pid"]] = roast
    return result


def split_name(name: str) -> dict | None:
    m = NAME_PATTERN.match(unicodedata.normalize("NFKC", name))
    if not m:
        return None
    base = re.sub(r"\s+", " ", m.group(1)).strip()
    weight = int(float(m.group(2)) * (1000 if m.group(3).lower() == "kg" else 1))
    return {"base": base, "weight": weight, "key": base.replace(" ", "")}


def fetch_detail(pid: str) -> tuple[str | None, bool]:
    html_text = fetch_html(f"{BASE_URL}/product/{pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    el = soup.select_one("div.detail_desc_box")
    text = el.get_text("\n", strip=True) if el else None
    in_stock = soup.select_one("input.cartaddinput") is not None
    return text, in_stock


def scrape_all_products() -> list[dict]:
    roasts = roast_by_pid()
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
        text, in_stock = fetch_detail(item["pid"])
        text = text or ""
        desc = re.sub(r"\s+", " ", text).strip()[:400] or None

        parsed = parse_product(base)
        is_blend = item["group"] == "blend" or "ブレンド" in base
        if is_blend:
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

        processing = parsed["processing_method"]
        if not is_blend and not processing:
            pm = re.search(r"精製方法\s+([^\s]+)", text)
            if pm:
                processing = normalize_processing_method(pm.group(1))
        if is_blend:
            processing = None

        records.append({
            "shop_name": SHOP_INFO["name"],
            "raw_name": base,
            "category": parsed["category"],
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": processing,
            "grade": parsed["grade"],
            "roast_level": roasts.get(item["pid"]),
            "roast_hint": None,
            "flavor_notes": desc,
            "farm_note": None,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": item["price"],
            "weight_g": weight,
            "stock_status": "販売中" if in_stock else "完売",
            "out_of_stock": not in_stock,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_shimizucoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_shimizucoffee.json に出力しました")


if __name__ == "__main__":
    main()
