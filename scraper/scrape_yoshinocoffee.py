# -*- coding: utf-8 -*-
"""
scrape_yoshinocoffee.py

自家焙煎珈琲専門店 よしの珈琲(https://yoshino-coffee.ocnk.net/、岩手県大船渡市盛町字内ノ目3-32)の珈琲豆の商品情報を取得する。おちゃのこネット(Ocnk)。

【対象商品について】
実データ確認済み(2026-11時点): 珈琲豆の全商品カテゴリ(product-list/19)の9商品(ブレンド2、シングルオリジン7)。
珈琲器具カテゴリは対象外。各商品は「250g/袋」と「100g/袋」を選べ(価格はちょうど2.5分の1ではなく概ね半額)、
100g(最小重量)を代表とする。豆のまま/粉(2種)を選べ、豆のままの価格を採用。
カートボタンが無い商品(ニカラグア、ケニア カリンドゥンドゥ、コスタリカ キサラ)は在庫切れ表示相当で、
重量別の価格が表示されないためカテゴリ一覧の価格(250g相当)・250gで出力し「完売」とする。
焙煎度は商品説明の【焙煎度】(ハイロースト=中煎り、シティロースト=中深煎り、フルシティロースト=深煎り、ミディアムロースト=中煎り)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name, detect_processing_method

SHOP_INFO = {
    "name": "自家焙煎珈琲専門店 よしの珈琲",
    "url": "https://yoshino-coffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "岩手県大船渡市盛町字内ノ目3-32",
    "prefecture": "岩手県",
    "robots_txt_status": "実質許可(2026-11-03確認。robots.txtはGPTBot・Bytespider等の特定クローラのみ全面禁止で、それ以外は制限なし。識別可能なUser-Agentを使用)",
    "source_note": "販売先 https://yoshino-coffee.ocnk.net/ の珈琲豆カテゴリ(product-list/19)と各商品ページ、特商法表示(/info)を2026-11-03に確認。住所は特商法表示(所在地 岩手県大船渡市盛町字内ノ目3-32、TEL 0192-26-2664)。"
                   "サイトのタイトル・説明に「自家焙煎珈琲店」「煎りたて・新鮮・香り豊かな自家焙煎珈琲豆を、岩手は三陸大船渡から全国へ」。更新日の記載なし(新商品欄あり)。",
    "last_verified_at": "2026-11-03",
}

BASE_URL = "https://yoshino-coffee.ocnk.net"
LIST_URL = f"{BASE_URL}/product-list/19"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
REQUEST_INTERVAL = 2
ROAST_MAP = [
    ("フルシティ、シティ", "中深煎り"),
    ("フルシティ", "深煎り"),
    ("シティ", "中深煎り"),
    ("ハイ", "中煎り"),
    ("ミディアム", "中煎り"),
]


def fetch_html(url: str) -> str:
    time.sleep(REQUEST_INTERVAL)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    soup = BeautifulSoup(fetch_html(LIST_URL), "html.parser")
    items = {}
    for cell in soup.select("li.list_item_cell"):
        a = cell.select_one("a.list_item_link")
        name_el = cell.select_one(".goods_name")
        if not (a and name_el):
            continue
        m = re.search(r"/product/(\d+)", a["href"])
        if not m or m.group(1) in items:
            continue
        price_el = cell.select_one(".selling_price .figure")
        pm = re.search(r"([\d,]+)", price_el.get_text()) if price_el else None
        items[m.group(1)] = {
            "pid": m.group(1),
            "name": re.sub(r"\s+", " ", unicodedata.normalize("NFKC", name_el.get_text(" ", strip=True))).strip(),
            "list_price": int(pm.group(1).replace(",", "")) if pm else None,
            "list_sold_out": "list_item_soldout" in cell.get("class", []),
        }
    return list(items.values())


def fetch_detail(pid: str) -> dict:
    html_text = fetch_html(f"{BASE_URL}/product/{pid}")
    soup = BeautifulSoup(html_text, "html.parser")
    body_text = soup.get_text("\n", strip=True)
    price100 = None
    m = re.search(r"100\s*g/袋\s*[・･]+\s*[￥¥]\s*([\d,]+)", unicodedata.normalize("NFKC", body_text).replace("・・・", "・・・"))
    if m:
        price100 = int(m.group(1).replace(",", ""))
    desc_el = soup.select_one(".detail_block_desc .detail_desc")
    text = desc_el.get_text(" ", strip=True) if desc_el else ""
    spec = {}
    for tr in soup.select(".detail_block_spec tr"):
        th, td = tr.find("th"), tr.find("td")
        if th and td:
            spec[re.sub(r"[\s【】]", "", th.get_text())] = re.sub(r"\s+", " ", td.get_text(" ", strip=True))
    return {"price100": price100, "text": text, "spec": spec, "purchasable": "カートに入れる" in html_text}


def main():
    records = []
    for item in list_items():
        det = fetch_detail(item["pid"])
        name = item["name"]
        d = det["spec"]
        desc = re.sub(r"\s+", " ", det["text"]).replace("商品詳細", "", 1).strip()[:400] or None
        is_blend = "ブレンド" in name
        parsed = parse_product(name)
        if is_blend:
            parsed["category"] = "ブレンド"
            parsed["origin_country"] = None
            parsed["origin_source"] = None
        else:
            parsed["category"] = "ストレート"
            if not parsed["origin_country"]:
                c = detect_country_name(name)
                if c:
                    parsed["origin_country"] = c
                    parsed["origin_source"] = "raw_name"
            parsed = apply_category_hint_fallback(parsed, name)
        proc = d.get("精製方法") or d.get("生産処理")
        if proc and detect_processing_method(proc):
            parsed["processing_method"] = detect_processing_method(proc)
        roast = None
        r = d.get("焙煎度", "")
        for key, val in ROAST_MAP:
            if r.startswith(key):
                roast = val
                break
        farm = " / ".join(f"{k}: {d[k]}" for k in ("地域", "農園名", "精製所", "生産者", "品種", "標高") if d.get(k)) or None
        if det["price100"] is not None:
            price, weight = det["price100"], 100
        else:
            price, weight = item["list_price"], 250  # 重量別の価格が非表示(在庫切れ)。一覧価格は250g相当
        sold_out = item["list_sold_out"] or not det["purchasable"]
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
            "flavor_notes": desc,
            "farm_note": farm,
            "post_processing_tags": parsed["post_processing_tags"],
            "blend_components": [],
            "price": price,
            "weight_g": weight,
            "stock_status": "完売" if sold_out else "販売中",
            "out_of_stock": sold_out,
            "product_url": f"{BASE_URL}/product/{item['pid']}",
        })

    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yoshinocoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yoshinocoffee.json に出力しました")
    for r in records:
        print(" ", r["raw_name"], "|", r["category"], r["origin_country"], r["processing_method"], r["roast_level"], r["price"], r["weight_g"], r["stock_status"])


if __name__ == "__main__":
    main()
