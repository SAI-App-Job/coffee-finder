# -*- coding: utf-8 -*-
"""
scrape_vankicoffee.py

ヴァンキコーヒーロースター(vankicoffee.com、愛知県名古屋市天白区池場
4-110、自家焙煎豆のオンライン販売)の商品情報を取得する。カラーミー
ショップ(vankicoffee.shop-pro.jpドメインで運用。vankicoffee.comは
店舗紹介用の静的サイトで、実際の通販機能はshop-pro.jpサブドメイン側に
ある)。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xmlに全52商品のpidリンクが直接含まれている
(なごやビーンズと異なりカテゴリページを介さず直接取得可能)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全52件のうちカリタ/ハリオ製のペーパーフィルター・
陶器製ドリッパー・コーヒーサーバー・コーヒーミル・細口ポット・
モカエキスプレス・カフェプレス・ドリップポット・メジャーカップ・
カプチーノ用ミルク泡立て器等の器具(20件)と「ギフトＢＯＸ」(空箱、
1件)が非対象。NON_BEAN_KEYWORDSで除外する。残り31件が焙煎豆単品
(缶入りの記念オリジナルブレンド「松岡正剛オリジナル【プレミアム缶入】」
を含む、価格帯が他の豆商品と同水準のため焙煎豆と判断)。

【重量について】
実データ確認済み: 各銘柄は100g/200g/300g/500gの4重量×6種の挽き方
(豆のまま/粗挽き/中挽き/中細挽き/細挽き/極細挽き)の組み合わせで
価格が重量に比例する(例: 100g=900円なら200g=1800円、300g=2700円、
500g=4500円)。商品ページ直下のsales_price(product-level)は常に
最小重量(100g)の価格と一致することを実データで確認済みのため、
misawacoffee/santoscoffeeと同様にproduct.sales_priceをそのまま採用し、
weight_gは100固定とする。

【flavor_notes(2026-09-20追記)】
実データ確認済み: 詳細ページの「煎り具合：」を含む<p>要素内に、多くの
ストレート商品は「産地：」ラベルより前に実際のテイスティング文が入って
いる(ブレンド商品は「産地：」自体を持たず「煎り具合：」から始まる)。
「産地：」または「煎り具合：」のうち先に出現するラベルの直前までを
flavor_notesとして採用する(tier1)。テイスティング文を持たない商品
(一部のブレンド・コロンビア・フレンチ等)は代わりに「フレーバー：AROMA
★★★／ACIDITY non／SWEET ★★／SMOKY ★★★」という★評価のフレーバー行を
flavor_notesとして採用する(tier2)。両方とも無い商品(松岡正剛オリジナル
【プレミアム缶入】、焙煎方法のみ記載)はflavor_notesを取得しない。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ヴァンキコーヒーロースター",
    "url": "https://vankicoffee.com/",
    "platform": "カラーミーショップ",
    "address": "愛知県名古屋市天白区池場4-110",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

SHOP_BASE_URL = "http://vankicoffee.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["カリタ", "ハリオ", "ギフト"]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
FLAVOR_PROSE_STOP_PATTERN = re.compile(r"産地[：:]|煎り具合[：:]")
FLAVOR_RATING_PATTERN = re.compile(r"フレーバー[：:]\s*(.+?)(?:\s*挽き具合は下記|$)", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "EUC-JP"
    return BeautifulSoup(resp.text, "html.parser")


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    target = None
    for p in soup.find_all("p"):
        if "煎り具合" in p.get_text():
            target = p
            break
    if not target:
        return None
    for br in target.find_all("br"):
        br.replace_with("\n")
    text = target.get_text().replace("\r", "")

    m = FLAVOR_PROSE_STOP_PATTERN.search(text)
    prose = text[:m.start()].strip() if m else text.strip()
    prose = re.sub(r"\s+", " ", prose).strip()
    if prose:
        return prose

    m2 = FLAVOR_RATING_PATTERN.search(text)
    if m2:
        rating = re.sub(r"\s+", " ", m2.group(1)).strip()
        return rating or None
    return None


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{SHOP_BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def build_record(soup: BeautifulSoup, product_url: str) -> dict | None:
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

    parsed = parse_product(title)
    price = product.get("sales_price_including_tax") or product.get("sales_price")

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(price) if price is not None else None,
            "product_url": product_url,
        }

    structural_out_of_stock = product.get("stock_num") == 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": 100,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_pid_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            detail = build_record(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
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
    with open("data_vankicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_vankicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
