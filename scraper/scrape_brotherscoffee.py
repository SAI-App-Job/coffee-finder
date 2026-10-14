# -*- coding: utf-8 -*-
"""
scrape_brotherscoffee.py

ブラザーズ・コーヒー(puroteajapan.jp、運営:有限会社プロテア・ジャパン、鳥取県米子市東福原7-4-18)の
自家焙煎コーヒー豆の商品情報を取得する。ショップサーブ(ShopServe、UTF-8)。

【住所について】
特定商取引法表示(/hpgen/HPB/shop/business.html)とお店案内(/hpgen/HPB/shop/shopguide.html)で
実データ確認済み(2026-10-13): 「有限会社 プロテア・ジャパン / 〒683-0802 鳥取県米子市東福原7-4-18」。

【対象商品について】
コーヒーカテゴリ(/SHOP/25761/list.html)の一覧を走査し、商品コード BCC* の豆のみ収録する。
ドリップバッグ(CD*)・セット(BCG*)は除外。BCC006「初回限定商品スペシャリティ珈琲」(1,000円、
重量・銘柄の明記なしのお試し用初回限定品)も除外。
重量は商品名の「200g」または仕様欄「製品重量」から取る(ブルーマウンテンNo.1は重量の記載なしでnull)。
価格は税込。在庫は詳細ページの「豆」行の在庫表示から判定する。
サイト内の最終更新が古め(店長日記・コラムは2022年中心、画像は2020〜2022年)で、在庫あり表示だが
実際の稼働は未確認。
"""

import json
import re
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "ブラザーズ・コーヒー",
    "url": "https://puroteajapan.jp/",
    "platform": "ショップサーブ",
    "address": "鳥取県米子市東福原7-4-18",
    "prefecture": "鳥取県",
    "robots_txt_status": "未確認",
}

BASE_URL = "https://puroteajapan.jp"
LIST_URL = f"{BASE_URL}/SHOP/25761/list.html"
REQUEST_HEADERS = {"User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"}
EXCLUDE_KEYWORDS = ("セット", "ギフト", "ドリップ", "初回限定", "お試し")
MAX_PAGES = 10

PRICE_PATTERN = re.compile(r"([\d,]+)\s*円")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gG]")
SPEC_WEIGHT_PATTERN = re.compile(r"製品重量\s*\n\s*(\d+)\s*[gG]")
ROAST_PATTERN = re.compile(r"(ライト|シナモン|ミディアム|ハイ|フルシティ|シティ|フレンチ|イタリアン)ロースト")

# 商品名に国名が無い銘柄の産地(商品説明で産地が明記されているもの)
ORIGIN_OVERRIDES = {
    "エンペラー珈琲": "ジャマイカ",      # 説明: ジャマイカのブルーマウンテン連峰産 ブルーマウンテンNo.1
    "アロハキングコーヒー": "アメリカ(ハワイ)",    # ハワイ・コナ
}


def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def list_items() -> list[dict]:
    items, seen = [], set()
    for page in range(1, MAX_PAGES + 1):
        url = LIST_URL if page == 1 else LIST_URL.replace("list.html", f"list{page}.html")
        soup = BeautifulSoup(fetch(url), "html.parser")
        new = 0
        for card in soup.select("div.layout1"):
            a = card.select_one("h2.goods a")
            if not a:
                continue
            href = a.get("href", "")
            if href in seen:
                continue
            seen.add(href)
            new += 1
            price_el = card.select_one("div.price")
            price_m = PRICE_PATTERN.search(price_el.get_text()) if price_el else None
            items.append({
                "title": re.sub(r"\s+", " ", a.get_text(strip=True)).strip(),
                "path": href,
                "price": int(price_m.group(1).replace(",", "")) if price_m else None,
            })
        if new == 0:
            break
    return items


def fetch_detail(path: str) -> dict:
    soup = BeautifulSoup(fetch(BASE_URL + path), "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    # 在庫: 「商品状態/在庫/購入」表の「豆」行
    stock_m = re.search(r"豆\s*\n\s*([^\n]+)", text[text.find("商品状態"):]) if "商品状態" in text else None
    stock_txt = stock_m.group(1).strip() if stock_m else ""
    sold_out = bool(stock_txt) and "在庫あり" not in stock_txt
    k = text.find("■ 商品説明")
    e = text.find("■ 商品仕様", k + 1) if k >= 0 else -1
    if k >= 0 and e < 0:
        e = text.find("関連商品", k)
    desc = re.sub(r"\s+", " ", text[k + len("■ 商品説明"):e].replace("\n", " ")).strip() if k >= 0 and e > k else None
    wm = SPEC_WEIGHT_PATTERN.search(text)
    return {"stock_txt": stock_txt, "sold_out": sold_out, "desc": desc,
            "spec_weight": int(wm.group(1)) if wm else None}


def build_record(item: dict, detail: dict) -> dict | None:
    title = item["title"]
    if any(kw in title for kw in EXCLUDE_KEYWORDS):
        return None
    norm = unicodedata.normalize("NFKC", title)
    weight_m = WEIGHT_PATTERN.search(norm)
    weight_g = int(weight_m.group(1)) if weight_m else detail["spec_weight"]
    name = re.sub(r"\s*\d+\s*[gG]\s*$", "", norm).strip()
    name = re.sub(r"\s+", " ", name)

    parsed = parse_product(name)
    if "ブレンド" in name:
        parsed["category"] = "ブレンド"
        parsed["origin_country"] = None
        parsed["origin_source"] = None
    else:
        override = next((c for k, c in ORIGIN_OVERRIDES.items() if name.startswith(k)), None)
        detected = override or detect_country_name(name)
        if detected and not parsed["origin_country"]:
            parsed["origin_country"] = detected
            parsed["origin_source"] = "raw_name" if detected in name else "description"
        parsed = apply_category_hint_fallback(parsed, name)

    desc = detail["desc"]
    rm = ROAST_PATTERN.search(desc or "")
    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": (rm.group(1) + "ロースト") if rm else None,
        "roast_hint": None,
        "flavor_notes": desc[:300] if desc else None,
        "farm_note": None,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": "完売" if detail["sold_out"] else "販売中",
        "out_of_stock": detail["sold_out"],
        "product_url": f"{BASE_URL}{item['path']}",
    }


def scrape_all_products() -> list[dict]:
    records = []
    for item in list_items():
        if not re.match(r"/SHOP/BCC\d+\.html$", item["path"]):
            continue
        if any(kw in item["title"] for kw in EXCLUDE_KEYWORDS):
            continue
        record = build_record(item, fetch_detail(item["path"]))
        if record is not None:
            records.append(record)
    return records


def main():
    records = scrape_all_products()
    output = {"shop": SHOP_INFO, "products": records}
    with open("data_brotherscoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_brotherscoffee.json に出力しました")


if __name__ == "__main__":
    main()
