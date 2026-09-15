# -*- coding: utf-8 -*-
"""
scrape_asabacoffee.py

麻葉珈琲(asabacoffee.base.shop、熊本県人吉市、自家焙煎豆のオンライン販売)
の商品情報を取得する。BASE。

【住所について】
特定商取引法ページ(https://asabacoffee.base.shop/law)で実データ確認済み
(2026-09時点): 会社名「つばめ交通株式会社」、事業者の名称「北昌二郎」、
事業者の所在地「〒8680008 熊本県人吉市中青井町３０６－６」との記載を確認。
一方、ABOUTページ(https://asabacoffee.base.shop/about)には店舗所在地として
「〒868-0003 熊本県人吉市紺屋町24」という異なる住所が掲載されている(実店舗の
所在地と考えられる)。他のBASE系スクレイパーと同様、法定表記(特定商取引法)
ページの住所を正として採用する。

【自家焙煎の実態について(候補リストの注記への対応)】
候補リストでは「麻葉珈琲は熊本市の珈琲回廊が運営元では」との懸念が付記されて
いたが、実データ確認の結果、ABOUTページに「ご注文頂いてから焙煎し、新鮮な
珈琲豆の販売をおこなっております」との明記があり、また特定商取引法ページの
運営会社は「珈琲回廊」ではなく地元の「つばめ交通株式会社」(人吉市中青井町)
であることを確認した。「珈琲回廊」への言及は一切見当たらず、人吉市内で
自家焙煎・販売していると判断し対象に含める。

robots.txt確認済み(2026-09時点): 他のBASE系店舗と同一の記述。curl/
python-requests等は個別にDisallow: /指定があるが、User-agent: *ルールでは
実質許可。本スクレイパーは識別可能な独自User-Agentを使用する。

【対象商品について】
実データ確認済み(全23件): sitemap.xmlの/items/配下23件のうち、実際の
焙煎豆単品(200g)は13件(オリジナルブレンド浅煎り・深煎り、エチオピア、
グアテマラ、ニカラグア、ルワンダ、パナマ、コロンビア、東ティモール、
パプアニューギニア、インド、インドネシア、デカフェメキシコ)。「オリジナル
キャニスター 200g」は豆が入る空き缶(容器)であり焙煎豆そのものではない
ため非対象。他はドリップバッグ(単品/デカフェ/ギフトボックス)・COLD BREW
PACK(水出し用)・ギフトセットのため非対象。NON_BEAN_KEYWORDSで除外する。

【重量について】
実データ確認済み: 商品名末尾に半角/全角の「200g」「200ｇ」表記があり、
これがそのまま(生豆換算の)重量として使われている(実際の焼き上がり重量は
160-170g程度になる旨が商品説明に記載されているが、他店舗と同様に商品名の
表記をそのままweight_gとして採用する)。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "麻葉珈琲",
    "url": "https://asabacoffee.base.shop/",
    "platform": "BASE",
    "address": "熊本県人吉市中青井町306-6",
    "prefecture": "熊本県",
    "robots_txt_status": "実質許可(2026-09確認。他のBASE系店舗と同一の記述。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://asabacoffee.base.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["ドリップバッグ", "ドリップバック", "COLD BREW", "ギフト", "キャニスター"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
TRAILING_WEIGHT_PATTERN = re.compile(r"[\s　]*\d+\s*[gｇ]\s*$")


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
    return {"title": title, "price": price}


def fetch_item_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "/items/" in loc.get_text()]


def base_name_and_weight(title: str) -> tuple[str, int | None]:
    weight_m = WEIGHT_PATTERN.search(title)
    weight_g = int(weight_m.group(1)) if weight_m else None
    base = TRAILING_WEIGHT_PATTERN.sub("", title).strip()
    return base, weight_g


def build_record(title: str, price: int | None, product_url: str) -> dict | None:
    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    if not WEIGHT_PATTERN.search(title):
        return None
    base_name, weight_g = base_name_and_weight(title)
    if not base_name:
        return None
    parsed = parse_product(base_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": base_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    stock_status = detect_stock_status(base_name)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": base_name,
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
        detail = build_record(fields["title"], fields["price"], product_url)
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
    with open("data_asabacoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_asabacoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
