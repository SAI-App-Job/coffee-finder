# -*- coding: utf-8 -*-
"""
scrape_kobecoffee.py

神戸珈琲物語(株式会社神戸珈琲、kobecoffee.jp、〒653-0827 兵庫県神戸市長田区
上池田6-8-23、自家焙煎豆のオンライン販売)の商品情報を取得する。
ショップサーブ(ShopServe)。本プロジェクトで初めてのショップサーブ店舗。

robots.txt確認済み(2026-09時点): /robots.txtが存在せず(404)、制限なし。

【プラットフォーム識別について】
実データ確認済み: 商品詳細ページに`application/ld+json`のProductGroup構造化
データ(schema.org)が埋め込まれており、画像CDNが`image1.shopserve.jp`
(ショップサーブ/GMOのカート基盤)であることから識別した。ProductGroupの
hasVariant(挽き方違いの選択肢。豆のまま/コーヒーメーカー/ペーパードリップ/
サイフォン/エスプレッソ等)は全て同一価格のため、先頭のvariantのoffersから
価格・在庫状況を取得すれば十分。

【商品一覧の取得方法について】
実データ確認済み: サイト全体(sitemap.xmlで115件の個別商品ページを確認)には
アイスリキッド・ドリップバッグ・ギフトセット・お菓子・雑貨等、自家焙煎
コーヒー豆そのものではない商品が大半を占める。「コーヒー豆 ブルーパック200g」
カテゴリページ(/SHOP/1124809/list.html、パンくずリストで確認)には該当する
単一銘柄の200g焙煎豆商品21件のみが掲載されており(ページ内に「21件中」と
表示、全件が1ページに収まる)、このカテゴリページを商品一覧の取得元とする。

【非コーヒー豆商品について】
上記の理由によりカテゴリページ経由でそもそも取得しないため、
NON_BEAN_KEYWORDSでの追加除外は不要(取得後の防御的チェックとしてのみ設置)。

【商品名の取得元について】
実データ確認済み: ld+json(ProductGroup)の"name"フィールドは「【神戸珈琲の
代表作_人気No.1】炭火ハウスブレンド...200g【ブルーパック】」のように
販促バッジや【ブルーパック】の位置が商品ごとに不揃い(先頭だったり末尾
だったりする)で商品名として使うには不安定。一方<title>タグは全件
「【ブルーパック】銘柄名 200g | コーヒー豆 ブルーパック200g | 神戸珈琲物語
公式通販 XXXXXXXX」の形式で一貫しているため、こちらを商品名の取得元とする。
先頭の「|」より前を商品名とし、【ブルーパック】接頭辞を除去する(末尾の
200gはweight_g抽出に使うためタイトルには残す)。全21件が200gのみで重量
バリエーションはないため、重複排除ロジックは不要。価格・在庫状況は
ld+jsonのhasVariant[0].offersから取得する(挽き方違いの選択肢は全て
同一価格)。

【カテゴリページのリンク抽出について】
実データ確認済み: カテゴリページには対象21件への相対パスリンク(href="/SHOP/
XXXXXXXX.html")の他に、「あわせて買われている商品」等のレコメンド枠に
他カテゴリの商品への絶対URLリンク(https://kobecoffee.jp/SHOP/10003200.html
等)やメルマガ登録リンク(/SHOP/mailmag.html)が混在する。相対パス
(href先頭が"/SHOP/"かつ数字/英数字+.htmlで終わる)のみに限定することで
正確に21件(ページ内表示の「21件中」と一致)を抽出する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "神戸珈琲物語",
    "url": "https://kobecoffee.jp/",
    "platform": "ショップサーブ",
    "address": "兵庫県神戸市長田区上池田6-8-23",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。/robots.txtが存在せず404、制限なし)",
}

BASE_URL = "https://kobecoffee.jp"
CATEGORY_URL = f"{BASE_URL}/SHOP/1124809/list.html"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "ドリップパック", "クイックコーヒー", "アイスリキッド",
    "ギフトセット", "コーヒーギフト", "ビーンズギフト", "インスタントコーヒー",
    "チョコレート", "羊羹", "フィナンシェ", "ゼリー", "レーズンサンド",
    "タンブラー", "リユーザブルカップ", "ペーパーフィルター", "キャリーバッグ",
    "紙袋", "マイボトルコーヒー", "お試しセット", "選べるブレンド", "せり上がりボックス",
    "カフェオレベース", "ピーナッツ", "クリーミーマイルド",
]
BLUE_PACK_PREFIX_PATTERN = re.compile(r"^【ブルーパック】")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_product_urls() -> list[str]:
    soup = fetch_page(CATEGORY_URL)
    pids: set[str] = set()
    for a in soup.select('a[href^="/SHOP/"]'):
        m = re.search(r"^/SHOP/([0-9A-Za-z]+)\.html$", a.get("href", ""))
        if m:
            pids.add(m.group(1))
    return [f"{BASE_URL}/SHOP/{pid}.html" for pid in pids]


def extract_fields(soup: BeautifulSoup, product_url: str) -> dict | None:
    title_el = soup.find("title")
    if not title_el:
        return None
    raw_title = title_el.get_text(strip=True)
    title = raw_title.split("|", 1)[0].strip()
    title = BLUE_PACK_PREFIX_PATTERN.sub("", title).strip()
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    ld_script = soup.find("script", type="application/ld+json")
    if not ld_script or not ld_script.string:
        return None
    try:
        data = json.loads(ld_script.string)
    except json.JSONDecodeError:
        return None
    entries = data if isinstance(data, list) else [data]
    product_group = next((e for e in entries if e.get("@type") == "ProductGroup"), None)
    if not product_group:
        return None

    variants = product_group.get("hasVariant") or []
    price = None
    structural_out_of_stock = True
    if variants:
        offer = variants[0].get("offers") or {}
        price_raw = offer.get("price")
        price = int(float(price_raw)) if price_raw is not None else None
        structural_out_of_stock = offer.get("availability") != "http://schema.org/InStock"

    return {
        "title": title,
        "price": price,
        "url": product_url,
        "structural_out_of_stock": structural_out_of_stock,
    }


def build_record(item: dict) -> dict | None:
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
            "product_url": item["url"],
        }

    stock_status = detect_stock_status(title, item["structural_out_of_stock"])
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
        "price": item["price"],
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["url"],
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_urls = fetch_product_urls()

    records = []
    flavored_records = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if not fields:
            continue

        detail = build_record(fields)
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
    with open("data_kobecoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_kobecoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
