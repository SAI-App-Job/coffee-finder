# -*- coding: utf-8 -*-
"""
scrape_80factory.py

ハチマル珈琲焙煎所(80factory.com、大阪府八尾市植松町4丁目8-23、自家焙煎豆の
オンライン販売)の商品情報を取得する。カラーミーショップ(shop-pro.jp旧ドメイン:
80factory.shop-pro.jp)。住所は自社サイトのアクセスページ
(https://80factory.com/access/ )で確認済み。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml上90件): ドリップバッグ各種(「ありがとうの、
専用ツール」シリーズ含む)、水出しアイスコーヒーバッグ、リキッド
アイスコーヒー(瓶入り)、オーツミルク、コーヒーフィルター(アバカ製)、
オリジナルウォーターボトル、各種ギフト・詰め合わせ・飲み比べセットが
非対象。また「グァテマラ＆インドネシア」のような「＆」で複数銘柄を
併記した2種アソートセットも単一銘柄の豆ではないため除外する
(NON_BEAN_KEYWORDSに"＆"".2種"を含める)。

【重量違いの重複/表記ゆれについて】
実データ確認済み: 同一銘柄が「【ビター 100g】インドネシア・アチェ
ワルズクナ農園」(100g)と「【送料無料/ビター系】インドネシア・アチェ
ワルズクナ 200g」(200g)、「【送料無料/ビター系 10%OFF】インドネシア・
アチェワルズクナ 400g（200g×2）」(実質400g)のように、【】内の
ロースト系統/送料無料ラベルが異なる形で複数登録されている。加えて
「ハチマルブレンド～ビター～」(100g)と「ハチマルブレンド ビター」
(200g/400g、送料無料系ラベル側の表記)のように波ダッシュの有無等の
表記ゆれもある。そのため基準名の算出時に、先頭の【】ラベル・商品番号
プレフィックス(例:「47｜」)・重量×個数の注記(例:「（200g×2）」)・
「N%OFF」・「・」「農園」「～」「〜」・空白を全て除去したうえで
グルーピングし、最小重量(100gがあれば100g)を代表として採用する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ハチマル珈琲焙煎所",
    "url": "https://80factory.com/",
    "platform": "カラーミーショップ",
    "address": "大阪府八尾市植松町4丁目8-23",
    "prefecture": "大阪府",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://80factory.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "水出しアイスコーヒー", "リキッドアイスコーヒー", "オーツミルク",
    "コーヒーフィルター", "ウォーターボトル", "ギフト", "セット", "飲み比べ",
    "＆", "2種", "２種",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|ｋｇ|[gｇ])", re.IGNORECASE)
BRACKET_PATTERN = re.compile(r"【[^】]*】")
ITEM_NO_PATTERN = re.compile(r"^\d+[｜|]")
MULTIPLIER_PATTERN = re.compile(r"[（(]\s*\d+\s*[gｇ]\s*[×xX]\s*\d+\s*[）)]")
PERCENT_OFF_PATTERN = re.compile(r"\d+[%％]OFF", re.IGNORECASE)
TOTAL_WEIGHT_BEFORE_PAREN_PATTERN = re.compile(r"(\d+)\s*[gｇ]\s*[（(]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    price = int(price) if price is not None else None
    structural_out_of_stock = product.get("stock_num") == 0
    return {"title": title, "price": price, "structural_out_of_stock": structural_out_of_stock}


def weight_key(title: str) -> float:
    # 「400g（200g×2）」のように合計重量が先頭に明記されている場合はそれを優先
    m = TOTAL_WEIGHT_BEFORE_PAREN_PATTERN.search(title)
    if m:
        return int(m.group(1))
    wm = WEIGHT_PATTERN.search(title)
    if not wm:
        return float("inf")
    value = int(wm.group(1))
    if "k" in wm.group(2).lower():
        value *= 1000
    return value


def base_name(title: str) -> str:
    t = BRACKET_PATTERN.sub("", title)
    t = ITEM_NO_PATTERN.sub("", t.strip())
    t = MULTIPLIER_PATTERN.sub("", t)
    t = PERCENT_OFF_PATTERN.sub("", t)
    t = WEIGHT_PATTERN.sub("", t)
    t = t.replace("・", "").replace("農園", "").replace("～", "").replace("〜", "")
    return re.sub(r"\s+", "", t).strip()


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base: dict[str, dict] = {}
    for item in items:
        key = base_name(item["title"])
        wkey = weight_key(item["title"])
        existing = by_base.get(key)
        if existing is None or wkey < weight_key(existing["title"]):
            by_base[key] = item
    return list(by_base.values())


def build_record(item: dict, product_url: str) -> dict | None:
    title = item["title"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": product_url,
        }

    stock_status = detect_stock_status(title, item.get("structural_out_of_stock", False))
    weight_g = weight_key(title)
    weight_g = None if weight_g == float("inf") else int(weight_g)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    all_items = []
    url_by_title: dict[str, str] = {}
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append(fields)
        url_by_title[fields["title"]] = product_url

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item, url_by_title[item["title"]])
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_80factory.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_80factory.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
