# -*- coding: utf-8 -*-
"""
scrape_kunikuni.py

カフェマルシェkunikuni(kunikunimame.com、東京都世田谷区経堂)の商品情報を
取得する。scrape_405coffee.py・scrape_etop.pyと同じカラーミーショップ
(shop-pro.jp)だが、テーマはPHILOCOFFEA/TSUKIKOYA系統に近い(li.productlist-unit、
var Colormeでの価格・バリアント取得)。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html; charset=EUC-JP)。
405coffee.py・etop.py等と同じく、requestsの自動判定に頼らずresp.encodingを
明示する。

【対象カテゴリについて】
トップページのカテゴリ一覧に「スペシャルティ珈琲豆(全ての豆27種)」
(cbid=1906626)という単一カテゴリがあり、これがコーヒー豆全件をカバーする。
「ギフト袋・ボックス」「コーヒー器具」という明確に非コーヒー豆の2カテゴリは
対象外。なおカテゴリ名の「27種」は実データ確認時点(2026-08)では実態と
食い違っており、実際にページネーションを辿って取得できたのは19件だった
(カテゴリ名の表示が更新されていないだけと考えられる)。表示名の数字ではなく、
実際にcrawlできた件数をそのまま採用する。

【焙煎度をグループ分類(パンくずリスト)から取得する】
実データ確認済み: 商品詳細ページのパンくずリスト(ul.topicpath-nav)に、
「スペシャルティ珈琲豆」グループとは別に、ミディアムロースト＋(浅煎り/6種)・
ハイロースト(中煎り/4種)・シティロースト(中深煎り/3種)・フルシティロースト
(深煎り/3種)・フレンチロースト(最深煎り/5種)という5つの焙煎度別グループへの
リンクが商品ごとに1つ含まれる。これらはROAST_LEVELSの8段階表記とそのまま
一致する店舗自身による正式な分類(CafeCafa・WOODBERRY COFFEEで見られたような
3段階の粗い自己申告や、ブレンド銘柄名との偶然の一致とは異なる)ため、
roast_hintではなく構造化されたroast_levelとして直接採用する
(detect_roast_level_from_breadcrumb参照。「フルシティロースト」が
「シティロースト」の部分文字列を含むため、判定順は長い方を先にする必要がある)。

【商品説明の構造】
div.product-order-expに「原産国：ブラジル・東ティモール」「品種：アカイア・
カツアイ/ハイブリッドティモール」という「ラベル：値」形式の行が2つ並び、
空行を挟んで自由記述(テイスティングノート)、さらに空行を挟んで重量別価格の
案内が続く(実データ確認済み)。構造化ラベルは原産国・品種の2つのみで、
生産処理・標高・農園等の欄は無い。ブレンド商品の原産国は複数の国名が
「・」区切りで並ぶのみで配合比率の記載が無いため、blend_componentsは
未対応とし、ブレンド商品のorigin_countryはNoneのままにする(Denim bis等と
同じ「産地国名のみ言及」パターン)。

【説明文中の\r由来の空行について】
実データ確認済み: 元のHTMLが各行の末尾に\r\n、さらに<br />タグそのものも
挟んでいるため、<br>を\nに変換した後の行分割では「原産国：...」の直後に
実質空文字列の行(\r由来)が挟まり、本来連続しているはずの「品種：...」行との
間に空行があるように見えてしまう。空行を「構造化フィールド終了」のシグナルと
して扱うと、この\r由来の空行1つで「品種」行に到達する前に読み取りを打ち切って
しまう不具合が実データで見つかった。そのため空行は常に読み飛ばし(継続)、
既知のラベル集合(KNOWN_DESC_LABELS)を両方取得できた時点、または未知の
ラベル・ラベル形式でない行に達した時点で終了する方式にしている
(parse_description_fields参照)。

【重量・価格: バリアントについて】
実データ確認済み: variantsのoption1_value(例:「200g  1250円」)に重量と
価格が1つの文字列で入っており、option2_valueは挽き方(豆のまま/各種挽き目)。
価格自体はoption_price_including_taxという構造化フィールドが別途あるため
そちらを使い、option1_valueからは正規表現で重量のみを取り出す。「豆のまま」
バリアントの中で最小重量のものを代表バリアントとして採用する
(405coffee.pyのpick_canonical_variant()と同じ考え方)。

【在庫について】
var Colorme のinventory_controlが"none"、stock_numは常にnull(実データ確認済み、
405coffee.pyと同じ運用)。構造化された在庫フラグが機能していないため、
商品名のテキストのみで在庫状態を判定する。

robots.txt確認済み(2026年8月時点): PHILOCOFFEA・405 COFFEE ROASTERS等と同一の
記述(User-agent: *は/secure/と/cart/のみ制限)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "カフェマルシェkunikuni",
    "url": "https://kunikunimame.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都世田谷区経堂2-4-8　Antelop経堂A号室",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA・405 COFFEE ROASTERS等と同一の記述)",
}

BASE_URL = "https://kunikunimame.com"
CATEGORY_ID = "1906626"  # スペシャルティ珈琲豆(全ての豆27種)。理由はモジュールdocstring参照
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
DESC_LABEL_PATTERN = re.compile(r"^(.+?)\s*：\s*(.+)$")
KNOWN_DESC_LABELS = {"原産国", "品種"}

# 理由はモジュールdocstring参照。「フルシティロースト」が「シティロースト」を
# 部分文字列として含むため、長い方を先に判定する
ROAST_GROUP_LABELS = ["フルシティロースト", "フレンチロースト", "ミディアムロースト", "ハイロースト", "シティロースト"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def parse_description_fields(text: str) -> dict:
    """「原産国：.../品種：...」の行を抽出する。理由はモジュールdocstring参照
    (\r由来の空行が実質的な行の間に挟まるため、空行は常に読み飛ばし、
    既知のラベルを両方取得できた時点か、未知のラベル・ラベル形式でない行に
    達した時点で終了する)。"""
    fields = {}
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        m = DESC_LABEL_PATTERN.match(line)
        label = m.group(1).strip() if m else None
        if not m or label not in KNOWN_DESC_LABELS:
            break
        fields[label] = m.group(2).strip()
        if KNOWN_DESC_LABELS <= fields.keys():
            break
    return fields


def detect_roast_level_from_breadcrumb(soup: BeautifulSoup) -> str | None:
    for a in soup.select('ul.topicpath-nav a[href*="mode=grp"]'):
        text = a.get_text(strip=True)
        for label in ROAST_GROUP_LABELS:
            if text.startswith(label):
                return label
    return None


def weight_from_variant(variant: dict | None) -> int | None:
    if not variant:
        return None
    m = WEIGHT_PATTERN.search(variant.get("option1_value") or "")
    return int(m.group(1)) if m else None


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """「豆のまま」バリアントの中で最小重量のものを代表バリアントとして選ぶ。
    理由はモジュールdocstring参照。"""
    if not variants:
        return None

    def weight_key(v):
        w = weight_from_variant(v)
        return w if w is not None else float("inf")

    whole_bean = [v for v in variants if "豆のまま" in (v.get("option2_value") or "")]
    pool = whole_bean or variants
    return min(pool, key=weight_key)


def build_record(product_url: str, colorme_product: dict, description_text: str, roast_level: str | None) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    variant = pick_canonical_variant(colorme_product.get("variants", []))
    price = variant.get("option_price_including_tax") if variant else None

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

    is_blend = parsed["category"] == "ブレンド"
    fields = parse_description_fields(description_text)

    origin_raw = fields.get("原産国")
    if origin_raw and not is_blend:
        country = detect_country_name(origin_raw)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": roast_level,
        "post_processing_tags": parsed["post_processing_tags"],
        "variety": None if is_blend else fields.get("品種"),
        "blend_components": [],  # 配合比率の記載が無いため未対応(理由はモジュールdocstring参照)
        "price": price,
        "weight_g": weight_from_variant(variant),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    desc_el = soup.select_one("div.product-order-exp")
    description_text = desc_el.get_text() if desc_el else ""
    roast_level = detect_roast_level_from_breadcrumb(soup)

    return build_record(url, colorme_product, description_text, roast_level)


def scrape_category_list_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/?mode=cate&cbid={CATEGORY_ID}&csid=0"
    if page > 1:
        url += f"&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.productlist-unit")

    results = []
    for item in items:
        title = None
        href = None
        for link in item.select('a[href*="pid="]'):
            text = link.get_text(strip=True)
            if text:
                title = text
                href = link.get("href", "")
                break
        if not title or not href:
            continue
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    all_list_items = {}
    page = 1
    while True:
        items = scrape_category_list_page(page)
        if not items:
            break
        for item in items:
            all_list_items[item["product_url"]] = item
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items.values():
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_kunikuni.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_kunikuni.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
