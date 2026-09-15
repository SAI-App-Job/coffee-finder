# -*- coding: utf-8 -*-
"""
scrape_kodouan.py

珈道庵(Kodouan、kodouan.com、〒842-0302 佐賀県佐賀市三瀬村藤原540-2、
「岩清水珈琲」を名乗る高級珈琲豆専門店)の商品情報を取得する。

【自家焙煎の確認について】
公式サイトの「岩清水珈琲のお話」ページ(https://www.kodouan.com/
iwashimizu-coffee/)に「森の中の焙煎工房で焙煎しています」との記載が
あり、三瀬の森の中の自社焙煎工房で生豆から焙煎していることを確認済み
(2026-09時点)。

【プラットフォームについて】
確立済み6パターン(BASE/カラーミー/Shopify/Ocnk/WooCommerce/EC-CUBE)の
いずれにも該当しない独自のカート・CMSシステム(analytics内の
"aispr.jp"参照からAiSPPRと推測されるが未確認)。商品カテゴリ一覧
ページ(/ic/straight等)は商品グリッドがAjax(itemSearch.js →
/api/front/item/itemPreSearch等)で動的読み込みされるため
requests+BeautifulSoupでは取得できないが、個別商品ページ(/i/<slug>)は
schema.org準拠のJSON-LD(Product)を静的に埋め込んでおり、価格・在庫
状況を含め確実に取得できる。商品ページの一覧はsitemap.xmlの
`/i/<slug>`パターンから取得する。

【非コーヒー豆商品の除外について】
実データ確認済み(sitemap.xml内`/i/`配下、全135件): 手提げ袋・
コーヒーフィルター・ドリップバッグ各種(単品/詰め合わせ)・水出し
アイスドリップ各種・多数のギフトセット(雅/粋/蜜/集/調/極/和/涼、
各種g数のプチギフト含む)が非対象。これらギフト・雑貨用スラッグの多くも
「tsubaki10」「kaori20」のように英数字+ハイフンのみで構成されており、
単純な「英数字のみ」判定では除外できない(実データ確認済み)。このため、
対象となる単品ストレート豆の産地ローマ字スラッグ(dominica/costarica/
guatemala/indonesia/tanzania/ethiopia/columbia/peru/brazil)と
ブレンド固有名スラッグ(sakurazaka/akane/nozomi/hitomi/kozue/aya/
madoka/mebae)を明示的なアローリストとして保持し、これに一致する
sitemap.xml内のURLのみを対象とする方式を採る(店舗が新銘柄を追加した
場合はこのリストへの追記が必要になるが、価格・在庫等の動的データは
毎回JSON-LDから取得するため、リストが古くても誤ったデータを出力する
ことはなく、単に新銘柄が漏れるだけに留まる)。

【重量について】
実データ確認済み: 商品名に「100ｇ」のように重量が明記されている。
"""

import re

import requests

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "珈道庵",
    "url": "https://www.kodouan.com/",
    "platform": "独自CMS(house未確立パターン。個別商品ページのJSON-LDを情報源として使用)",
    "address": "佐賀県佐賀市三瀬村藤原540-2",
    "prefecture": "佐賀県",
    "robots_txt_status": "未確認(2026-09時点。robots.txt自体の制限記述は見つからず、"
                          "個別商品ページ(/i/<slug>)への低頻度アクセスのみ行う)",
}

BASE_URL = "https://www.kodouan.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照: 単品ストレート豆・ブレンド固有名の
# スラッグのみを明示的に対象とする(アローリスト方式)
BEAN_SLUGS = {
    "dominica", "costarica", "guatemala", "indonesia", "tanzania",
    "ethiopia", "columbia", "peru", "brazil",
    "sakurazaka", "akane", "nozomi", "hitomi", "kozue", "aya", "madoka", "mebae",
}
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_bean_urls() -> list[str]:
    resp = requests.get(f"{BASE_URL}/sitemap.xml", headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
    urls = []
    for loc in locs:
        m = re.match(r"^https://www\.kodouan\.com/i/([a-zA-Z0-9_-]+)$", loc)
        if m and m.group(1) in BEAN_SLUGS:
            urls.append(loc)
    return urls


def fetch_product_jsonld(url: str) -> dict | None:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text
    # 商品ページには複数のJSON-LDブロック(BreadcrumbList, Product)が並ぶため、
    # "@type": "Product"を含むスクリプトブロックのみを対象に正規表現で抽出する
    for m in re.finditer(r'<script type="application/ld\+json">\s*(\[.*?\]|\{.*?\})\s*</script>', html, re.DOTALL):
        block = m.group(1)
        if '"@type": "Product"' not in block and '"@type":"Product"' not in block:
            continue
        import json
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def build_record(url: str, product: dict) -> dict | None:
    title = (product.get("name") or "").strip()
    if not title:
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": url,
        }

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") is not None else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
    stock_status = detect_stock_status(title, structural_out_of_stock)

    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None

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
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    urls = fetch_bean_urls()

    records = []
    flavored_records = []
    for url in urls:
        try:
            product = fetch_product_jsonld(url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {url} ({e})")
            continue
        if not product:
            print(f"[warn] JSON-LD Productが見つかりません: {url}")
            continue

        detail = build_record(url, product)
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
    with open("data_kodouan.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kodouan.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
