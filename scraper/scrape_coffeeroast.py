# -*- coding: utf-8 -*-
"""
scrape_coffeeroast.py

豆工房コーヒーロースト宇都宮店(shop.coffee-roast.net、栃木県宇都宮市
菊水町8-21、自家焙煎豆のオンライン販売)の商品情報を取得する。
カラーミーショップ。

robots.txt確認済み(2026-09時点): 他のカラーミー店舗と同一の記述。
User-agent: *に対し/secure/・/cart/のみDisallow。AhrefsBot等一部
ボットを個別にDisallow: /、それ以外は制限なし。

【店頭お渡し/宅配便の重複について】
実データ確認済み(全136件): ほぼ全ての銘柄が「(銘柄名)」(宅配便)と
「(銘柄名)【店頭お渡し】」(店頭引き渡し限定、価格は同一)のペアで重複
登録されている。「【店頭お渡し】」を除いた基準名でグルーピングし、
宅配便版(【店頭お渡し】を含まない側)を優先して採用する。宅配便版が
無く店頭お渡し版のみ存在する銘柄(コマヤグアSHG等)はそのまま採用する。

【非コーヒー豆商品の除外について】
実データ確認済み: ローストアーモンド/カシューナッツ/ピスタチオ(素焼き
ナッツ)・各種ペーパーフィルター/ドリッパー/コーヒーサーバー/フラワー
ドリッパー・ストレートココア・レーズン/デーツ(ドライフルーツ)・
COFFEE OTEDAMA(雑貨)・有機アガベシロップ・ベルメーレンカラメル
ビスケット各種・水出しアイスコーヒー(液体)・ドリップバッグ・
「ネット限定 こみこみパック」(既存銘柄の割引セット)・ドス・カフェ
テラスのキャラメル菓子・コーヒーはち蜜・馬毛ブラシ・クイックサーモ
(温度計)・かんたんドリップ(ペーパー)・プレミアムショコラ(チョコ
レート菓子)がコーヒー豆単品ではないためNON_BEAN_KEYWORDSで除外する。
商品名が空の削除済みプレースホルダーレコードも除外する。

【空白表記ゆれによる除外漏れについて】
実データ確認済み(初回実行で発覚): 除外対象の「プレミアムショコラ」が
宅配便版では空白なし、店頭お渡し版では「プレミアム ショコラ【店頭お
渡し】」と空白ありで登録されており、キーワード一致判定(空白なし
"プレミアムショコラ"で判定)が店頭お渡し版だけすり抜けて残っていた。
判定対象の文字列側の空白を完全に除去してから比較するよう修正した。

【店頭お渡し版のみ産地名が重複表記される問題について】
実データ確認済み(初回実行で発覚): 「ペルー 有機栽培」(宅配便版)に対し
店頭お渡し版だけ「ペルー 有機栽培（ペルー）」と末尾に産地名が括弧書きで
重複表記されており、【店頭お渡し】除去だけでは基準名が一致せず別銘柄
として両方残ってしまっていた。末尾の括弧の中身がそれより前の部分文字列
としてすでに登場している場合に限りその括弧を除去するよう修正した
(グラポス農協（メキシコ）等、正当な産地注記の括弧は対象外)。
"""

import json
import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "豆工房コーヒーロースト宇都宮店",
    "url": "https://coffee-roast.net/",
    "platform": "カラーミーショップ",
    "address": "栃木県宇都宮市菊水町8-21",
    "prefecture": "栃木県",
    "robots_txt_status": "実質許可(2026-09確認。他のカラーミー店舗と同一の記述。"
                          "/secure/・/cart/のみDisallow。AhrefsBot等一部ボットを"
                          "個別にDisallow: /、それ以外は制限なし)",
}

BASE_URL = "https://shop.coffee-roast.net"
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "ローストアーモンド", "ローストカシューナッツ", "ローストピスタチオ",
    "ペーパーフィルター", "V60", "有田焼", "ドリップポット", "フラワードリッパー",
    "コーヒーサーバー", "ビーカーサーバー", "ストレートココア", "レーズン", "デーツ",
    "OTEDAMA", "アガベシロップ", "ビスケット", "水出しアイスコーヒー", "ドリップバッグ",
    "こみこみパック", "クリームキャラメル", "はち蜜", "馬毛ブラシ", "クイックサーモ",
    "かんたんドリップ", "円すいコーヒーフィルター", "プレミアムショコラ",
]
COLORME_PATTERN = re.compile(r"var Colorme\s*=\s*(\{.*?\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
WHITESPACE_PATTERN = re.compile(r"[\s　]+")
TRAILING_PAREN_PATTERN = re.compile(r"[（(]([^（）()]+)[）)]\s*$")
TENTOU_WATASHI = "【店頭お渡し】"


def contains_keyword(title: str) -> bool:
    # 理由: 「プレミアム ショコラ【店頭お渡し】」(空白あり)と「プレミアム
    # ショコラ」(空白なし、宅配便版)のように、除外対象商品でも宅配便版と
    # 店頭お渡し版で空白の有無が不揃いなことがある(実データ確認済み)。
    # キーワード側に空白を含めなくても両方の表記を確実に検出できるよう、
    # 判定対象の文字列は空白を完全に除去してから比較する。
    normalized = WHITESPACE_PATTERN.sub("", title)
    return any(kw in normalized for kw in NON_BEAN_KEYWORDS)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_pid_urls() -> list[str]:
    soup = fetch_page(f"{BASE_URL}/sitemap.xml")
    urls = []
    for loc in soup.find_all("loc"):
        text = loc.get_text(strip=True)
        if "pid=" in text:
            urls.append(text)
    return urls


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
    data = json.loads(m.group(1))
    product = data.get("product") or {}
    title = (product.get("name") or "").strip()
    if not title or contains_keyword(title):
        return None

    price = product.get("sales_price_including_tax") or product.get("sales_price")
    structural_out_of_stock = product.get("stock_num") == 0
    return {
        "title": title,
        "price": int(price) if price is not None else None,
        "url": product_url,
        "structural_out_of_stock": structural_out_of_stock,
    }


def dedup_key(title: str) -> str:
    base_name = title.replace(TENTOU_WATASHI, "").strip()
    # 理由: 「ペルー 有機栽培」(宅配便版)と「ペルー 有機栽培（ペルー）」
    # (店頭お渡し版)のように、店頭お渡し版だけ末尾に産地名を括弧書きで
    # 重複表記しているケースが実データで見つかった(【店頭お渡し】除去
    # だけでは別銘柄と誤判定される)。末尾の括弧の中身が、それより前の
    # 部分文字列としてすでに登場している場合に限り、その括弧を除去する
    # (グラポス農協（メキシコ）やハワイコナ（アメリカ）のように、括弧内が
    # 前方に出現しない正当な産地注記は除去しない)。
    m = TRAILING_PAREN_PATTERN.search(base_name)
    if m and m.group(1) in base_name[: m.start()]:
        base_name = base_name[: m.start()].strip()
    return base_name


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, dict] = {}
    for item in items:
        base_name = dedup_key(item["title"])
        is_tentou = TENTOU_WATASHI in item["title"]
        existing = by_base_name.get(base_name)
        if existing is None:
            by_base_name[base_name] = item
        elif TENTOU_WATASHI in existing["title"] and not is_tentou:
            # 既存が店頭お渡し版のみで、今回宅配便版が見つかった場合は差し替える
            by_base_name[base_name] = item
    return list(by_base_name.values())


def build_record(item: dict) -> dict | None:
    title = item["title"].replace(TENTOU_WATASHI, "").strip()
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
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_coffeeroast.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_coffeeroast.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
