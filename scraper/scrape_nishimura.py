# -*- coding: utf-8 -*-
"""
scrape_nishimura.py

神戸にしむら珈琲店(株式会社にしむらコーヒーサービス、kobe-nishimuracoffee.shop、
〒650-0004 兵庫県神戸市中央区中山手通1-26-3(中山手本店)、昭和23年創業。
自家焙煎は灘区大石東町6-1-13の「灘珈琲工房」で行っている)の商品情報を取得
する。カラーミーショップ。

【店舗数の確認について(11店舗未満ルール)】
実データ確認済み: 本体サイト(kobe-nishimura.jp)の店舗情報ページ
(/shop/all.html)本文に「神戸市内外に９店舗を展開。そのうち１店舗は、旧会員制
喫茶店『北野坂にしむら珈琲店』です」と明記されている。会社概要ページ
(/company/index.html)の店舗一覧でも、中山手本店・北野坂にしむら珈琲店・
三宮店・阪急前店・ハーバーランド店・芦屋店・御影店・梅田店(大阪市)・元町店の
9店舗(うち芦屋・梅田は兵庫県外)+但馬牛石焼ステーキみかげ館(飲食併設店)+
灘工房(焙煎施設、非店舗)+事務所を確認。9店舗<11店舗のため対象に含める。
自家焙煎(灘珈琲工房)も確認済み。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【文字コードについて】
実データ確認済み: レスポンスのContent-Typeヘッダーがcharset=EUC-JPを明示
しており、requestsが自動的に正しくデコードするため特別な対応は不要。

【商品一覧の取得方法について】
実データ確認済み: sitemap.xml(143件のpid付きURL)を商品一覧の取得元とする。
このうち3件(pid=180873222/192740215/192746593)は404となり実在しない
(サイトマップに残った削除済み商品と判断)。取得失敗時はスキップする。

【重量違いの重複について】
実データ確認済み: 単一銘柄の焙煎豆15種が全て〈100g〉/〈200g〉の2サイズ
(価格は正確に2倍)で個別商品登録されている。商品名末尾の重量表記を除いた
基準名でグルーピングし、最小重量(100g)を代表として採用する。

【「お試し20g」の除外について】
実データ確認済み: 上記15銘柄それぞれに対応する「お試し コーヒー豆 20g
(銘柄名)」という試供品サイズが別商品として10件register されている
(全銘柄ではなく一部)。通常サイズ(100g/200g)と別枠の試供品パックであり、
商品名の構造も異なる(括弧内に銘柄名を埋め込む形式)ため、NON_BEAN_KEYWORDS
の「お試し」で除外する(本プロジェクトの他店舗でも「お試しセット」等は
一貫して除外対象としている)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全143件(取得成功140件)のうちドリップバッグ(単品/各種
アソートギフト)・焼き菓子(セセシオンブランドのギフト箱/ショートブレッド/
バウムクーヘン/レープクーヘン/ケーゼゲベック等)・チョコレート(珈琲ビーンズ
チョコレート/ナッツ＆珈琲チョコレート)・紅茶(にしむらゴールドティー)・
ジャム・雑貨(カップ&ソーサー/マグカップ/アイスグラス/ウォーターグラス/
手ぬぐい/ひざ掛け)・器具(メリタのグラスポット/ペーパーフィルター)・
真空缶入り(通常の袋詰めとは別パッケージ)・キャニスター入り・複数銘柄の
詰め合わせ(3種/4種詰め合わせ、コーヒー豆4種セット等)・各種ギフトセット
(缶/焼き菓子/紅茶/カップ等との組み合わせ)が非対象。NON_BEAN_KEYWORDSで
除外する。商品名が空の削除済みプレースホルダーレコードも除外する。

【「【初めての方へ】にしむらオリジナルブレンド 300g」について】
実データ確認済み: 他の単一銘柄と異なり100g/200gではなく300gのみの単独
商品(「にしむらオリジナルブレンドホット」100g/200gペアとは別商品として
サイト側で独立登録されている)。初回購入者向けの案内接頭辞
「【初めての方へ】」を除去した上で、そのまま単独銘柄として対象に含める。

【在庫状況について】
実データ確認済み: 大半の商品でstock_num=None(在庫管理対象外の定番商品)。
一部商品(エチオピア サムライ・ナチュラル100g/200g等)でstock_num=0
(在庫切れ)を確認。ルールに従い欠品商品も削除せずout_of_stockフラグ付きで
結果に含める。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "神戸にしむら珈琲店",
    "url": "https://kobe-nishimuracoffee.shop/",
    "platform": "カラーミーショップ",
    "address": "兵庫県神戸市中央区中山手通1-26-3",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://kobe-nishimuracoffee.shop"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ドリップバッグ", "セセシオンの焼き菓子", "チョコレート", "ショートブレッド",
    "カップ", "ソーサー", "手ぬぐい", "アイスグラス", "ウォーターグラス",
    "ゴールドティー", "ひざ掛け", "真空缶", "キャニスター", "詰め合わせ", "セット",
    "ジャム", "紅茶", "ペーパーフィルター", "グラスポット", "ギフト", "バウムクーヘン",
    "ケーゼゲベック", "ティータイム", "レープクーヘン", "シュトレンエッケ",
    "お試し", "エリーゼン",
]
FIRST_TIME_PREFIX_PATTERN = re.compile(r"^【初めての方へ】")
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ㎏]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def extract_fields(soup: BeautifulSoup, product_url: str) -> dict | None:
    script_text = ""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "var Colorme" in text:
            script_text = text
            break

    m = COLORME_PATTERN.search(script_text)
    if not m:
        return None
    import json
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = re.sub(r"<br\s*/?>", " ", product.get("name") or "").strip()
    title = re.sub(r"\s+", " ", title)
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None
    title = FIRST_TIME_PREFIX_PATTERN.sub("", title).strip()

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    structural_out_of_stock = product.get("stock_num") == 0
    return {
        "title": title,
        "price": int(price) if price is not None else None,
        "url": product_url,
        "structural_out_of_stock": structural_out_of_stock,
    }


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = WEIGHT_PATTERN.sub("", item["title"]).strip()
        weight_m = WEIGHT_PATTERN.search(item["title"])
        weight_key = int(weight_m.group(1)) if weight_m else float("inf")
        existing = by_base_name.get(base_name)
        existing_weight_m = WEIGHT_PATTERN.search(existing["title"]) if existing else None
        existing_weight = int(existing_weight_m.group(1)) if existing_weight_m else float("inf")
        if existing is None or weight_key < existing_weight:
            by_base_name[base_name] = item
    return list(by_base_name.values())


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
    weight_g = None
    if weight_m:
        weight_g = int(weight_m.group(1)) * 1000 if "㎏" in weight_m.group(0) else int(weight_m.group(1))

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
    product_urls = fetch_pid_urls()

    all_items = []
    for product_url in product_urls:
        try:
            fields = extract_fields(fetch_page(product_url), product_url)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")
            continue
        if fields:
            all_items.append(fields)

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
    with open("data_nishimura.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_nishimura.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
