# -*- coding: utf-8 -*-
"""
scrape_yuukacoffee.py

ゆうかCoffee(千葉県浦安市北栄、店主・増田による自家焙煎)の自社EC(www.yuukacoffee.com、EC-CUBE 4系)の
商品情報を取得する。

【対象】全59件のうち、名称末尾が「200g入」の焙煎豆(シングル・ブレンド・デカフェ)。
除外: 「お得な500gパック」(200g×2袋と同額の同一銘柄の重複商品)、おすすめセット(プラチナ/彩り/定番/スモール)、
コーヒーバッグ、ギフトセット・ギフト箱、ペーパーフィルター。
【価格・重量】挽き方(豆のまま/粉に挽く/エスプレッソ用)によらず同額のため、classCategories の
price02_inc_tax(税込)を採用。重量は商品名の「200g入」。
【在庫】classCategories の stock_find が全て false なら品切れ。
robots.txt: User-agent: * に対し /*.csv$ のみ禁止(2026-10-26確認)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback

SHOP_INFO = {
    "name": "ゆうかCoffee",
    "url": "https://www.yuukacoffee.com/",
    "platform": "EC-CUBE 4系(独自ドメイン)",
    "address": "千葉県浦安市北栄1-1-13 岩波ビル1F",
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-10-26確認。User-agent: * に /*.csv$ のみDisallow)",
    "source_note": "自社EC(https://www.yuukacoffee.com/products/list)の商品一覧と各商品ページを2026-10-26に確認。"
                   "住所は公式のショップ情報(https://www.yuukacoffee.com/user_data/shopinfo)、"
                   "自家焙煎は公式(https://www.yuukacoffee.com/user_data/abouts)に基づく。"
                   "200g入の豆のまま価格を採用。500gパック(200g×2と同額の重複)・セット・コーヒーバッグ・ギフトは除外",
    "last_verified_at": "2026-10-26",
}

BASE_URL = "https://www.yuukacoffee.com"
LIST_URL = BASE_URL + "/products/list?disp_number=60&pageno={page}"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+https://github.com/SAI-App-Job/coffee-finder; contact: https://x.com/SaiCoffea)"}
REQUEST_INTERVAL = 2.0

EXCLUDE_NAME_KEYWORDS = ["500g", "セット", "バッグ", "ギフト", "フィルター", "ペーパー"]
WEIGHT_RE = re.compile(r"(\d+)\s*g\s*入")
ROAST_LABEL_RE = re.compile(r"(極深煎り|中深煎り|深煎り|中浅煎り|浅煎り|中煎り)")
CLASS_MARKER = "eccube.classCategories = "

_last = [0.0]


def fetch(url: str) -> str:
    wait = REQUEST_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=25)
    _last[0] = time.time()
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_product_ids() -> list[str]:
    ids: list[str] = []
    page = 1
    while True:
        html_text = fetch(LIST_URL.format(page=page))
        found = re.findall(r'/products/detail/(\d+)"', html_text)
        new = [p for p in dict.fromkeys(found) if p not in ids]
        if not new:
            break
        ids.extend(new)
        page += 1
    return ids


def extract_leaves(html_text: str) -> list[dict]:
    i = html_text.find(CLASS_MARKER)
    if i < 0:
        return []
    start = html_text.find("{", i)
    depth = 0
    for k in range(start, len(html_text)):
        if html_text[k] == "{":
            depth += 1
        elif html_text[k] == "}":
            depth -= 1
            if depth == 0:
                break
    try:
        cc = json.loads(html_text[start:k + 1])
    except json.JSONDecodeError:
        return []
    leaves = []
    for outer in cc.values():
        for v in outer.values():
            if v.get("product_class_id"):
                leaves.append(v)
    return leaves


def parse_detail(pid: str) -> dict | None:
    url = f"{BASE_URL}/products/detail/{pid}"
    html_text = fetch(url)
    soup = BeautifulSoup(html_text, "html.parser")
    h = soup.select_one(".ec-productRole__title h2") or soup.select_one("h2.ec-headingTitle")
    if not h:
        return None
    name = unicodedata.normalize("NFKC", h.get_text(strip=True))
    name = re.sub(r"\s+", " ", name).strip()
    if any(k in name for k in EXCLUDE_NAME_KEYWORDS):
        return None
    wm = WEIGHT_RE.search(name)
    if not wm:
        return None
    weight = int(wm.group(1))

    leaves = extract_leaves(html_text)
    if not leaves:
        return None
    price = int(leaves[0]["price02_inc_tax"].replace(",", ""))
    in_stock = any(l.get("stock_find") for l in leaves)

    root = soup.select_one(".ec-productRole")
    for x in root(["script", "style"]):
        x.decompose()
    cats = [a.get_text(strip=True) for a in root.select(".ec-productRole__category a")]
    cat_text = " ".join(cats)
    desc_el = root.select_one(".ec-productRole__description")
    desc = desc_el.get_text("\n", strip=True) if desc_el else ""
    desc_lines = [l for l in desc.split("\n") if l.strip()]
    # 商品一覧のキャッチ文(説明文の冒頭)を風味メモにする
    flavor_notes = " ".join(desc_lines[:2])[:200] or None

    parsed = parse_product(name)
    is_blend = "ブレンド" in cat_text or "ブレンド" in name
    if is_blend:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        parsed["category"] = "ストレート"
        parsed = apply_category_hint_fallback(parsed, name)

    roast = None
    rm = ROAST_LABEL_RE.search(name) or ROAST_LABEL_RE.search(desc)
    if rm:
        roast = rm.group(1)
    if not roast and "少し深く焙煎" in desc:
        roast = "深煎り"

    sold_out = (not in_stock) or ("品切れ" in root.get_text())
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast,
        "roast_hint": None,
        "flavor_notes": flavor_notes,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight,
        "stock_status": "完売" if sold_out else "販売中",
        "out_of_stock": sold_out,
        "product_url": url,
    }


def scrape_all_products() -> list[dict]:
    records = []
    for pid in list_product_ids():
        try:
            rec = parse_detail(pid)
        except requests.RequestException as e:
            print(f"[warn] 取得失敗 {pid}: {e}")
            continue
        if rec:
            records.append(rec)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_yuukacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yuukacoffee.json に出力しました")


if __name__ == "__main__":
    main()
