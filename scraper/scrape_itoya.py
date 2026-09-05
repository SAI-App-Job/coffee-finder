# -*- coding: utf-8 -*-
"""
scrape_itoya.py

伊東屋珈琲(itoyacoffee.com、群馬県桐生市相生町2-588-75〈運営: 伊東屋珈琲
合同会社〉、2005年から自家焙煎に取り組む自家焙煎豆のオンライン販売)の
商品情報を取得する。カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【重量・挽き方バリエーションについて】
実データ確認済み: 焙煎豆の商品名には「【100g・200g・500g・1kg】」の
ように選択可能な重量が列挙されているが、実際の重量・価格は個別ページ
ではなくproduct.variants配列(option1_value=挽き方、option2_value=重量)
に構造化データとして入っている(熊谷珈琲と同じColorme系JSON方式)。
「豆のまま」のうち最小重量(100g)を代表バリアントとして採用する。
商品名の【100g・200g・500g・1kg】表記自体はraw_nameからは取り除かず
そのまま残す(店舗の表記をそのまま尊重、weight_gはvariants側の実測値を
使う)。

【option1/option2の順序が商品によって逆転する問題について】
実データ確認済み(初回実行で発覚): 大半の商品はoption1_value=挽き方・
option2_value=重量だが、「インドネシア スマトラ タケンゴン」等一部の
商品ではoption1_value=重量・option2_value=挽き方と順序が逆になって
いた。片方のフィールドのみを前提にすると、順序が逆の商品でweight_gが
すべてNoneになってしまう(価格は基準価格sales_price_including_taxに
フォールバックするため偶然100g価格と一致し、この不具合に気付き
にくい)。修正: 「豆のまま」判定・重量抽出のいずれも両方のフィールド
(option1_value・option2_value)を対象にするよう変更した。

【非コーヒー豆商品の除外について】
実データ確認済み: 全61件のうちリキッドコーヒー・コーヒーゼリー・
ドリップバッグ/コーヒーバッグ(単品・アソート・ギフト箱各種)・水出し
コーヒー・コーヒーギフトA〜D・缶入りコーヒーギフト・オリジナルマグ
カップ/トートバッグ/ステンレス製ボトル/タンブラー・コーヒー保存缶・
ドリンク2種/3種セット各種・コーヒー牛乳のもとがコーヒー豆単品では
ないためNON_BEAN_KEYWORDSで除外する。商品名が空の削除済み
プレースホルダーレコードも除外する。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "伊東屋珈琲",
    "url": "https://itoyacoffee.com/",
    "platform": "カラーミーショップ",
    "address": "群馬県桐生市相生町2-588-75",
    "prefecture": "群馬県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://itoyacoffee.com"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "リキッドコーヒー", "コーヒーゼリー", "ドリップバッグ", "コーヒーバッグ",
    "水出しコーヒー", "コーヒーギフト", "マグカップ", "トートバッグ",
    "ステンレス", "タンブラー", "保存缶", "ドリンク", "コーヒー牛乳",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    return [loc.get_text(strip=True) for loc in soup.find_all("loc") if "pid=" in loc.get_text()]


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    # 理由: option1_value/option2_valueのどちらに重量・挽き方が入るかが
    # 商品によって逆転していることが実データで判明した(例:「インドネシア
    # スマトラ タケンゴン」はoption1_value=重量/option2_value=挽き方だが、
    # 「ハウスブレンド」はoption1_value=挽き方/option2_value=重量)。
    # 固定フィールドを前提にすると一方の並びでweight_gがNoneになって
    # しまうため、両方のフィールドを対象に「豆のまま」判定と重量抽出を
    # 行う。
    def is_whole_bean(v):
        return "豆のまま" in (v.get("option1_value") or "") or "豆のまま" in (v.get("option2_value") or "")

    def extract_weight(v):
        for key in ("option1_value", "option2_value"):
            m = WEIGHT_PATTERN.search(v.get(key) or "")
            if m:
                return int(m.group(1))
        return None

    bean_variants = [v for v in variants if is_whole_bean(v)]
    pool = bean_variants or variants
    candidates = [(extract_weight(v), v) for v in pool]
    candidates = [(w, v) for w, v in candidates if w is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda c: c[0])[1]


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
    variants = product.get("variants") or []
    variant = pick_canonical_variant(variants)
    price = variant.get("option_price_including_tax") if variant else (
        product.get("sales_price_including_tax") or product.get("sales_price")
    )
    weight_g = None
    if variant:
        for key in ("option1_value", "option2_value"):
            wm = WEIGHT_PATTERN.search(variant.get(key) or "")
            if wm:
                weight_g = int(wm.group(1))
                break

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
    with open("data_itoya.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_itoya.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
