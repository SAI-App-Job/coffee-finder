# -*- coding: utf-8 -*-
"""
scrape_yamashitacoffee.py

やました珈琲(yamashita-coffee.ocnk.net、鹿児島県鹿屋市寿5丁目14-7、自家
焙煎珈琲豆屋)の商品情報を取得する。おちゃのこネット(Ocnk)。

robots.txt確認済み(2026-09時点): 他のOcnk店舗と同一の記述。User-agent: *
には制限なし(GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ
Disallow: /で本スクレイパーは該当しない)。

【住所について】
特定商取引法ページ(https://yamashita-coffee.ocnk.net/info、Ocnkでは
「/info」が特定商取引法表示ページ)で実データ確認済み(2026-09時点):
「所在地」欄に「鹿児島県鹿屋市寿５丁目１４－７」(全角数字表記)との記載を
確認。候補リストの住所(半角表記)と一致。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlの/product/N形式の個別商品ページへのリンクが
28件含まれており、全件コーヒー豆単品(除外対象の詰め合わせ・器具等は無い)。
商品名には「＜9％OFF価格＞」のような割引率の注記が付くが、これは表示上の
注記であり価格自体はproduct:price:amountメタタグの値(税込・割引後)を
そのまま採用する。

【価格未掲載商品について】
実データ確認済み: 「タンザニア KIBO AA（別名キリマンジャロ）500g」
(product/45)のみ、価格メタタグが存在せず、本文に「販売価格はお問い合わせ
ください。」と表示される(価格非公開・要問い合わせ)。この商品は同一銘柄の
250g版(product/44、価格1,550円)と重量違いの重複関係にあるため、後述の
「最小重量を代表として採用する」ロジックにより自動的に250g版が選ばれ、
価格非公開の500g版は結果に含まれない(特別な除外処理は不要)。

【重量違いの重複について】
実データ確認済み: 全銘柄が250g/500gの2種類の重量で別々の商品ページとして
登録されている(バリアントではない)。商品名末尾の「◯◯ｇ＜割引注記＞」を
除いた基準名でグルーピングし、最小重量(250g)を代表として採用する。

【産地判定の注意】
「カロシ・トラジャ」(product/31・32)は実際にはカロシ地区とトラジャ地区
双方の豆を指す複合的な銘柄名だが、coffee_parser.pyの特定銘柄マスタでは
辞書の挿入順により「トラジャ」が先にマッチし、designated_brand="トラジャ"
として判定される(産地国自体はいずれもインドネシアで変わらないため実害は
無い)。

【flavor_notes(2026-09-21追記)】
実データ確認済み: 商品詳細ページのdiv.item_descに短いテイスティング文が
直接入っている(対象14件全て確認、価格・スペック等の混入なし)。全文を
そのまま採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "やました珈琲",
    "url": "https://yamashita-coffee.ocnk.net/",
    "platform": "おちゃのこネット",
    "address": "鹿児島県鹿屋市寿5丁目14-7",
    "prefecture": "鹿児島県",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *には制限なし。"
                          "GPTBot/Bytespider/TikTokSpider/meta-externalagentのみ"
                          "Disallow: /で本スクレイパーは該当しない)",
}

BASE_URL = "https://yamashita-coffee.ocnk.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WEIGHT_TAIL_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*[<＜].*$")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [
        loc.get_text(strip=True) for loc in soup.find_all("loc")
        if re.search(r"/product/\d+$", loc.get_text(strip=True))
    ]


def extract_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = re.sub(r"\s+", " ", title_el["content"].strip())
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    for br in soup.find_all("br"):
        br.replace_with("\n")
    desc_el = soup.select_one("div.item_desc")
    flavor_notes = desc_el.get_text("\n", strip=True) if desc_el else None
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = WEIGHT_TAIL_PATTERN.sub("", title).strip()
    return base, weight_g


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base, weight_g = base_name_and_weight(item["title"])
        item = {**item, "base_name": base, "weight_g": weight_g}
        weight_key = weight_g if weight_g is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None:
            by_base_name[base] = item
            continue
        existing_weight = existing["weight_g"] if existing["weight_g"] is not None else float("inf")
        if weight_key < existing_weight:
            by_base_name[base] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["base_name"]
    if not title or item["price"] is None:
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item["price"],
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title)

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
        "flavor_notes": item.get("flavor_notes"),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": item["price"],
        "weight_g": item["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        all_items.append({
            "title": fields["title"], "price": fields["price"], "url": product_url,
            "flavor_notes": fields.get("flavor_notes"),
        })

    canonical_items = pick_canonical_items(all_items)

    records = []
    flavored_records = []
    for item in canonical_items:
        detail = build_record(item)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)

    return records, flavored_records


if __name__ == "__main__":
    import json

    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_yamashitacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamashitacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
