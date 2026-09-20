# -*- coding: utf-8 -*-
"""
scrape_yamatokawa.py

ヤマとカワ珈琲店(yamatokawa.shop-pro.jp、長野県木曽郡木曽町開田高原末川
2799-1〈開田高原焙煎所、特定商取引法上の登録地〉、長野店は長野市鶴賀
田町2252、自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【非コーヒー豆商品の除外について】
実データ確認済み: 全111件のうちドリップバック各種(単品/セット/まとめ
買い)・カフェオレベース各種・水出しコーヒーパック・ギフト各種(A〜D、
こだわりの器セット、詰合せ)・手ぬぐい・コーヒーメジャー/フィルター
ホルダー/ミル/ドリッパー/V60/ネルドリップ/ビーカーサーバー/セラー
メイト/ドリップポット(器具)・チョコレート/クッキー/飴菓子/マグカップ/
コーヒーカップ/お菓子詰め合わせ/シュトーレン(食品・什器)・オンライン
講座・リキッドコーヒー・オリジナルキャップが非対象。
NON_BEAN_KEYWORDSで除外する(「セット」を包括的なキーワードとして採用、
実データで対象の焙煎豆銘柄に「セット」を含むものが無いことを確認済み)。
残り15件(焙煎豆)を対象とする。重量表記が商品名に無く単一サイズ販売の
ため重量重複処理は不要。

【flavor_notes(2026-09-20追記)】
実データ確認済み: 詳細ページのdiv.product_expにテイスティング文が
入る構造だが、対象21件中20件はこの要素自体が空/存在せず(商品説明文が
そもそも書かれていない)、季節限定の1件「アイスコーヒーブレンド」のみ
実際に星評価付きのテイスティング文が入っていた。取得できる情報源が
そもそも乏しいためカバレッジは低い(1/21)が、抽出ロジック自体は正しく
機能しており、店舗側が今後説明文を追加した場合に備えて実装する。この
1件はブログ記事調で複数の「■見出し」区切りの長文だったため、最初の
「■見出し」の本文(2番目の見出しの直前まで)のみを採用する(それ以降は
在庫過多の経緯等、テイスティングと無関係な内容のため)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ヤマとカワ珈琲店",
    "url": "https://yamatokawa.shop-pro.jp/",
    "platform": "カラーミーショップ",
    "address": "長野県木曽郡木曽町開田高原末川2799-1",
    "prefecture": "長野県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://yamatokawa.shop-pro.jp"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバック", "カフェオレベース", "水出しコーヒーパック", "セット",
    "手ぬぐい", "コーヒーメジャー", "フィルターホルダー", "ミル", "ドリッパー",
    "V60", "ネルドリップ", "ビーカーサーバー", "セラーメイト", "ドリップポット",
    "チョコ", "クッキー", "飴菓子", "マグカップ", "コーヒーカップ", "お菓子",
    "シュトーレン", "講座", "リキッドコーヒー", "キャップ",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def split_into_paragraphs(el) -> list[str]:
    paragraphs = []
    current_parts: list[str] = []
    for child in el.contents:
        name = getattr(child, "name", None)
        if name == "br":
            continue
        text = child.get_text() if name else str(child)
        text = text.strip()
        if not text:
            if current_parts:
                paragraphs.append(" ".join(current_parts))
                current_parts = []
        else:
            current_parts.append(text)
    if current_parts:
        paragraphs.append(" ".join(current_parts))
    return paragraphs


def extract_flavor_notes(soup: BeautifulSoup) -> str | None:
    """理由はモジュールdocstring参照。"""
    el = soup.select_one("div.product_exp")
    if not el:
        return None
    paras = split_into_paragraphs(el)
    heading_idx = [i for i, p in enumerate(paras) if p.startswith("■")]
    if len(heading_idx) >= 2:
        body = paras[heading_idx[0] + 1:heading_idx[1]]
    elif len(heading_idx) == 1:
        body = paras[heading_idx[0] + 1:]
    else:
        body = [p for p in paras if "★" not in p and "☆" not in p and "：" not in p]
    text = " ".join(body).strip()
    return text or None


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
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
        "flavor_notes": extract_flavor_notes(soup),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": int(price) if price is not None else None,
        "weight_g": weight_g,
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
    with open("data_yamatokawa.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yamatokawa.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
