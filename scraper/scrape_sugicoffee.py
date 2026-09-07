# -*- coding: utf-8 -*-
"""
scrape_sugicoffee.py

スギコーヒーロースティング(sugicoffee.comが公式情報サイト、実際の通販は
beans-club.com、愛知県高浜市湯山町5-2-3〈高浜ロースタリー(本店)〉+刈谷店
(愛知県刈谷市中山町2-37-1)、自家焙煎豆のオンライン販売)の商品情報を取得
する。カラーミーショップ(Shop-Pro)。

【ドメインについて】
実データ確認済み(2026-09時点): sugicoffee.com(タイトル「TOP│名古屋近郊
コーヒー豆販売｜スギコーヒーロースティング」)がブランド公式サイトで、
サイト内の「SHOPPING」「通販専用サイト」リンクは全てbeans-club.com側を
指している。事業者所在地は公式サイトの店舗一覧ページ(高浜ロースタリー
(本店)：愛知県高浜市湯山町5-2-3、刈谷店：愛知県刈谷市中山町2-37-1)で
確認済み。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【商品名の連番プレフィックスについて】
実データ確認済み(全39件): コーヒー豆商品の商品名は「00-」「01-」等の
2桁連番+ハイフンが先頭に付く(表示順制御用の内部プレフィックスで商品名の
一部ではない)。産地判定等に影響しないようbuild_record内で除去してから
parse_productに渡す。ドリップバッグ等の非対象商品は「oo-」(アルファベット
のオー)表記で紛れており、これらはNON_BEAN_KEYWORDSで別途除外する。

【重量について】
実データ確認済み: 全商品が「豆のまま/中挽き/エスプレッソ用挽き」×
「100g/250g/500gパック」の変則命名(全角/半角g混在、「パック」の有無も
商品ごとに不統一)で9通りの組み合わせを持ち、商品名自体には重量表記が
無い。ページ先頭のsales_price_including_taxは常に最小重量(100g・豆の
まま)の価格と一致するため、100gをこの店の固定重量として採用する。

【非コーヒー豆商品の除外について】
実データ確認済み(全39件のsitemap.xml掲載商品): アバカ製ペーパー
フィルター各種(5件)・コーヒー教室(初級/中級×2/上級、4件)・季節限定
水出しアイスコーヒーパック(1件)・簡単便利！おいしいコーヒーバッグ
(1件、ブレンド3種から選ぶ個包装ドリップ)・【送料込み】シングル
オリジン/オリジナルブレンドのバラエティセット×3種(250g×3種類の
詰め合わせ、3件)が非対象。NON_BEAN_KEYWORDSで除外する。また商品名が
空(削除済み、id=0)のプレースホルダーが4件あり、こちらもタイトル空
チェックで除外する。残り21件(コーヒー豆)を対象とする。

【価格0円の商品について】
実データ確認済み: 一部商品(ニカラグア ラ・ベンディシオン農園パカマラ等
5件)はstock_num=0かつ全バリアントのoption_price(_including_tax)が0円
になっている(在庫切れ・販売終了扱いだが商品ページ自体は残存)。他店
(misawacoffee等)と同じロジックで扱い、価格はそのまま0を保持しつつ
stock_num==0をstructural_out_of_stockとしてdetect_stock_status()に渡す。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "スギコーヒーロースティング",
    "url": "https://sugicoffee.com/",
    "platform": "カラーミーショップ",
    "address": "愛知県高浜市湯山町5-2-3",
    "prefecture": "愛知県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://beans-club.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "アバカ", "フィルター", "コーヒー教室", "水出しアイスコーヒーパック",
    "コーヒーバッグ", "セット",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
NUMBER_PREFIX_PATTERN = re.compile(r"^[0-9oO]{2}-\s*")
# 理由はモジュールdocstring参照(重量表記が無く全商品共通で100g単位)
FIXED_WEIGHT_G = 100
ROAST_HINT_TERMS = ["中深煎り", "中浅煎り", "極深煎り", "浅煎り", "中煎り", "深煎り"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def extract_roast_hint(title: str) -> str | None:
    for term in ROAST_HINT_TERMS:
        if term in title:
            return term
    return None


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
    raw_title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    raw_title = re.sub(r"\s+", " ", raw_title)
    if not raw_title:
        return None
    title = NUMBER_PREFIX_PATTERN.sub("", raw_title).strip()
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
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": extract_roast_hint(title),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": FIXED_WEIGHT_G,
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
    with open("data_sugicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_sugicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
