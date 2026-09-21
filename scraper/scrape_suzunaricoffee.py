# -*- coding: utf-8 -*-
"""
scrape_suzunaricoffee.py

suzunari coffee(shop.suzunaricoffee.com、〒875-0062 大分県臼杵市野田持田120、
自家焙煎豆のオンライン販売)の商品情報を取得する。BASE(独自ドメイン)。

【プラットフォームについて】
候補リストでは「shop.suzunaricoffee.com」というサブドメイン形式やJPY/USD
通貨切替・言語切替UIからShopifyとの誤認の可能性があったが、実データ確認済み
(2026-09時点): 商品ページのCSSが「cf-baseassets.thebase.in」から配信されて
おり、metaタグ「copyright: BASE」・og:titleの「powered by BASE」表記から
実際にはBASE(独自ドメイン)であることを確認した。products.jsonエンドポイント
は存在せず(ホームにリダイレクトされる)、他のBASE系店舗と同様にsitemap.xml +
商品ページのOGPメタタグ方式で取得する。

【住所について】
特定商取引法ページ(https://shop.suzunaricoffee.com/law)で実データ確認済み
(2026-09時点): 事業者の名称「匹田貴明」、事業者の所在地「〒8750062
大分県臼杵市野田持田120」との記載を確認。候補リストの住所と一致。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(全52件): sitemap.xmlの/items/配下52件のうち、商品名に
重量表記の無い定番サイズの焙煎豆単品は7件(Kenya Gichathaini AA・
緩緩[かんかん]2026・エチオピア Hambella Guji・Nicaragua El Cambalache
Maracaturra Natural・刻刻[こくこく]・Guatemala Buena Vista・
【デカフェ】メキシコ エルトリウンフォ)。個別の商品ページ本文
(「内容量：200g(1袋)」表記)で全て200gであることを確認済み。
「【1kg】エチオピア グジ」「【2kg】エチオピア グジ」等のkg単位の大容量
パックは、上記と同一銘柄の業務用大容量版(重複)のため除外する。他は
定期便(サブスクリプション)・琲蜜(カフェオレベース)・ドリップバッグ各種・
ギフトセット各種・詰め合わせ(スタンダード100g×3種/お試しアソート60g×5種)・
手ぬぐい/T-shirt/water bottle/moon calendar等の雑貨・Rib食器シリーズ・
Clever Coffee Dripper/ペーパーフィルター等の器具・ドリップバッグ
オリジナルラベル制作(印刷サービス)・「【K様】ご注文商品」(特定顧客向け
専用注文)のため非対象。NON_BEAN_KEYWORDSで除外する。

【flavor_notes(2026-09-21追記)】
実データ確認済み: og:descriptionに対象7件全てで産地スペック+カップ
コメント(テイスティング要素)が入っている。末尾に「内容量：200g(1袋)」
または(この内容量表記が省略されている場合は)「※1袋、2袋の場合は…」
という配送方法案内の定型文が続くため、この見出しの直前で打ち切る。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "suzunari coffee",
    "url": "https://shop.suzunaricoffee.com/",
    "platform": "BASE",
    "address": "大分県臼杵市野田持田120",
    "prefecture": "大分県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.suzunaricoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

STANDARD_WEIGHT_G = 200  # 実データ確認済み(商品ページ本文「内容量：200g(1袋)」)
NON_BEAN_KEYWORDS = [
    "定期便", "琲蜜", "手ぬぐい", "T-shirt", "Drip Bag", "ドリップバッグ",
    "ORIGINAL GIFT", "GIFT SET", "RUSK", "ラスク", "スタンダード", "アソート",
    "【1kg】", "【2kg】", "ARIGATOU", "gift box", "WATER BOTTLE", "calendar",
    "STARTER SET", "【Rib】", "Dripper", "paper filter", "ラベル制作", "様】ご注文商品",
]
FLAVOR_STOP_PATTERN = re.compile(r"内容量：200g|※1袋、2袋の場合は")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return BeautifulSoup(resp.text, "html.parser")


def extract_og_fields(soup: BeautifulSoup) -> dict | None:
    title_el = soup.select_one('meta[property="og:title"]')
    if not title_el or not title_el.get("content"):
        return None
    title = title_el["content"].split(" | ")[0].strip()
    price_el = soup.select_one('meta[property="product:price:amount"]')
    price = int(float(price_el["content"])) if price_el and price_el.get("content") else None
    desc_el = soup.select_one('meta[property="og:description"]')
    flavor_notes = desc_el["content"].strip() if desc_el and desc_el.get("content") else ""
    m = FLAVOR_STOP_PATTERN.search(flavor_notes)
    if m:
        flavor_notes = flavor_notes[:m.start()].strip()
    return {"title": title, "price": price, "flavor_notes": flavor_notes or None}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def build_record(title: str, price: int | None, product_url: str, flavor_notes: str | None = None) -> dict | None:
    if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
        return None
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
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
        "flavor_notes": flavor_notes,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": STANDARD_WEIGHT_G,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    item_urls = fetch_item_urls()

    records = []
    flavored_records = []
    for product_url in item_urls:
        try:
            fields = extract_og_fields(fetch_page(product_url))
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue
        detail = build_record(fields["title"], fields["price"], product_url, fields.get("flavor_notes"))
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
    with open("data_suzunaricoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_suzunaricoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
