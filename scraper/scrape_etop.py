# -*- coding: utf-8 -*-
"""
scrape_etop.py

珈琲店トップ(etop.shop-pro.jp、カラーミーショップ/shop-pro.jp、運営: 渋谷食品株式会社)の
商品情報を取得する。東京都渋谷区代々木の単独店舗。

scrape_405coffee.pyをテンプレートに実装しているが、同じshop-pro.jpでもこのショップは
異なるテーマ(c-item-list系クラス、dl.additionalによる商品詳細)を使っている
(実データ確認済み、2026-08時点)。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html; charset=EUC-JP)。
405coffee.py・rhizomag.py等と同じく、requestsの自動判定に頼らずresp.encodingを
明示する。

【対象カテゴリを3つに絞る理由】
トップページのカテゴリメニュー(実データ確認済み、2026-08時点)は7つ:
SPECIALITY & PREMIUM(cbid=2898996)/STRAIGHT COFFEE(cbid=254133)/
MIXED COFFEE(cbid=251894)/DRIP BAGS(cbid=254138)/FOODS & DRINKS
(cbid=2899383)/EQUIPMENT(cbid=254139、0件)/TOP DAY(cbid=257636)。
このうち採用したのは最初の3つのみ:
- FOODS & DRINKS・EQUIPMENTはコーヒー豆ではない
- DRIP BAGS(2件)は実データ確認の結果、いずれもトップミックス/風/薫味の
  3種を5袋ずつ詰め合わせたギフトセットで、単一の産地・焙煎度を持つ商品では
  ないため対象外とした
- TOP DAY(3件)は実データ確認の結果、商品名に「9月トップデー」のように
  発送月が固定で埋め込まれた期間限定の再掲(既存のトップミックス/風/薫味を
  月替わりで割引販売しているだけ)であり、月をまたぐと商品名が実態と
  食い違う。恒久的なカタログとして扱うべきではないため対象外とした

【生豆(未焙煎豆)の除外について】
実データ確認済み: SPECIALITY & PREMIUMカテゴリに【※生豆】【スペシャリティ】
ブルーマウンテンNo.1のような未焙煎の生豆販売が混在している。焙煎豆と同じ
dl.additional構造を持つため構造的な判別はできず、商品名の「生豆」という
キーワードで除外する。

【dl.additionalのラベルが商品ごとに異なる点について】
実データ確認済み: エリア/生産国or産地/地域/グレードor品種・等級orスクリーン/製法、
という組み合わせが商品によって一部欠けたり順序が違ったりする(PHILOCOFFEAの
BEANS DATA表と同じ「汎用ラベル抽出」方式で対応、parse_additional_fields参照)。
「エリア」は「アフリカ」「アジア」のような大陸レベルの粗い区分なので、
「地域」(産地の詳細)が無い場合のみregion_detailのフォールバックとして使う。

【「標高」ラベルの値が実際には精選方法を指している実データ上の誤表記について】
実データ確認済み(pid=192991422 モカシダモ G-4): dl.additionalの【標高】欄に
「非水洗式（ナチュラル）」という精選方法の値が入っており、店舗側の入力ミスと
考えられる。ALTITUDE_LIKE_PATTERNで値が標高らしい数字+m表記かどうかを判定し、
そうでなくかつ【製法】欄が別途無い場合のみ、この値を精選方法として救済する
(標高欄としては採用しない=数字が無いのでparse_altitudeは自然に不一致となり
架空の標高を作らない)。

【標高の表記ゆれについて】
実データ確認済み: 「1000m〜1600m」(数字それぞれにm付き)と「1,650〜1,800m」
(末尾にのみm)の両方の表記がある。前者に対応するため、範囲パターンの1つ目の
数字直後の「m」は任意(オプション)としている。

【価格・重量: バリアントについて】
実データ確認済み: variantsは「豆のまま/粉：ペーパードリップ」のような挽き方
違い(重量は商品名に固定、例:「モカシダモ G-4 100g」)の場合と、
「100g/1kg」のような重量違い(価格が変わる)の場合の両方がある(pid=188243037で
確認済み)。option1_valueから正規表現で重量を検出できるバリアントが1つでも
あれば最小重量を代表バリアントとして採用し、無ければ(=重量は商品名にしか
出ない)「豆のまま」を優先する(405coffee.pyのpick_canonical_variant()と同じ
考え方)。重量自体はバリアントから取れなければ商品名からのフォールバックで拾う。
405coffee.pyのWEIGHT_PATTERNは「g」表記のみを想定しているが、本ショップは
「1kg」表記も実在するため、kg→g換算を含むparse_weight_grams()を別途用意している。

【在庫について】
実データ確認済み: var Colorme のproduct.stock_numは商品によってnull(未追跡)
と整数(バリアント在庫数の合計、追跡あり)の両方が存在する。整数の場合のみ
構造的な品切れシグナルとして使い(0以下で品切れ)、null の場合は商品名の
テキストのみで判定する(405coffee.pyと同じ考え方)。

robots.txt確認済み(2026-08時点): User-agent: * は /secure/ と /cart/ のみ制限
(商品ページ・カテゴリページは対象外)。AhrefsBot等のSEO分析系ボットは
個別に全面禁止されているが、本スクレイパーはそれらを名乗らない。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "珈琲店トップ",
    "url": "https://etop.shop-pro.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都渋谷区代々木5-63-10",
    "prefecture": "東京都",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。"
                          "PHILOCOFFEA・405 COFFEE ROASTERS等と同一の記述)",
}

BASE_URL = "https://etop.shop-pro.jp/"
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照。DRIP BAGS(254138)・FOODS & DRINKS(2899383)・
# EQUIPMENT(254139)・TOP DAY(257636)は対象外
TARGET_CATEGORIES = {
    2898996: "SPECIALITY & PREMIUM",
    254133: "STRAIGHT COFFEE",
    251894: "MIXED COFFEE",
}

NON_BEAN_KEYWORDS = ["生豆"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
WEIGHT_PATTERN = re.compile(r"([\d.]+)\s*(kg|g|ｇ)", re.IGNORECASE)
ALTITUDE_LIKE_PATTERN = re.compile(r"\d[\d,]*\s*m")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*m?\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")


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


def parse_additional_fields(soup: BeautifulSoup) -> dict:
    """dl.additionalのdt/ddペアを汎用的にキーバリュー抽出する。理由はモジュール
    docstring参照(店舗によってラベルの組み合わせが異なるため)。"""
    dl = soup.select_one("dl.additional")
    if not dl:
        return {}
    dts = dl.select("dt")
    dds = dl.select("dd")
    fields = {}
    for dt, dd in zip(dts, dds):
        label = dt.get_text(strip=True).rstrip("：:")
        value = dd.get_text(strip=True)
        if label and value:
            fields[label] = value
    return fields


def parse_altitude(altitude_text: str | None) -> tuple[int | None, int | None]:
    if not altitude_text:
        return None, None
    text = unicodedata.normalize("NFKC", altitude_text)
    text = re.sub(r"\s", "", text)
    m = ALTITUDE_RANGE_PATTERN.search(text)
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    m = ALTITUDE_SINGLE_PATTERN.search(text)
    if m:
        value = int(m.group(1).replace(",", ""))
        return value, value
    return None, None


def parse_weight_grams(text: str | None) -> int | None:
    """「100g」「1kg」のいずれの表記からもグラム数を取り出す
    (405coffee.pyのWEIGHT_PATTERNは「g」表記のみ対応だが、本ショップは
    「1kg」表記も実在するため、kg→g換算を追加している)。"""
    if not text:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    m = WEIGHT_PATTERN.search(normalized)
    if not m:
        return None
    value = float(m.group(1))
    if m.group(2).lower() == "kg":
        value *= 1000
    return int(value)


def weight_from_variant(variant: dict | None, fallback_text: str = "") -> int | None:
    if variant:
        weight = parse_weight_grams(variant.get("option1_value"))
        if weight is not None:
            return weight
    return parse_weight_grams(fallback_text)


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    """理由はモジュールdocstring参照。重量が分かるバリアントがあれば最小重量を、
    無ければ「豆のまま」を優先する。"""
    if not variants:
        return None

    def weight_of(v):
        return parse_weight_grams(v.get("option1_value"))

    weighted = [v for v in variants if weight_of(v) is not None]
    if weighted:
        return min(weighted, key=weight_of)

    whole_bean = [v for v in variants if "豆のまま" in (v.get("option1_value") or "")]
    pool = whole_bean or variants
    return pool[0]


def build_record(product_url: str, colorme_product: dict, fields: dict, category_hint: str) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        variant = pick_canonical_variant(colorme_product.get("variants", []))
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant.get("option_price_including_tax") if variant else None,
            "product_url": product_url,
        }

    # サイト自身が明示するMIXED COFFEE区分を一次情報として優先する(「トップミックス」
    # 「風」等のブレンド銘柄名は商品名に「ブレンド」を含まないため、商品名からの
    # BLEND_KEYWORDS判定では検出できない)
    if category_hint == "MIXED COFFEE":
        parsed["category"] = "ブレンド"
    is_blend = parsed["category"] == "ブレンド"

    origin_raw = fields.get("生産国") or fields.get("産地")
    if origin_raw:
        country = detect_country_name(origin_raw)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, category_hint)

    altitude_raw = fields.get("標高")
    processing_raw = fields.get("製法")
    altitude_min, altitude_max = None, None
    if altitude_raw:
        normalized = unicodedata.normalize("NFKC", altitude_raw)
        if ALTITUDE_LIKE_PATTERN.search(normalized):
            altitude_min, altitude_max = parse_altitude(altitude_raw)
        elif not processing_raw:
            # 理由はモジュールdocstring参照(【標高】欄への精選方法の誤入力の救済)
            processing_raw = altitude_raw

    if processing_raw:
        parsed["processing_method"] = normalize_processing_method(processing_raw)

    grade = fields.get("グレード") or fields.get("品種・等級") or fields.get("スクリーン")
    region_detail = fields.get("地域") or fields.get("エリア")

    if (
        not fields
        and not parsed.get("origin_country")
        and not is_blend
    ):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": product_url,
        }

    variant = pick_canonical_variant(colorme_product.get("variants", []))
    stock_num = colorme_product.get("stock_num")
    structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else parsed["processing_method"],
        "grade": None if is_blend else grade,
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": None if is_blend else region_detail,
        "altitude_min_m": None if is_blend else altitude_min,
        "altitude_max_m": None if is_blend else altitude_max,
        "blend_components": [],  # ブレンド商品の産地別内訳は実データ(dl.additionalが存在しない)で未対応
        "price": variant.get("option_price_including_tax") if variant else None,
        "weight_g": weight_from_variant(variant, title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str) -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    fields = parse_additional_fields(soup)
    return build_record(url, colorme_product, fields, category_hint)


def scrape_category_list_page(cbid: int, page: int) -> list[dict]:
    url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0"
    if page > 1:
        url += f"&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.c-item-list__item")

    results = []
    for item in items:
        link_el = item.select_one("div.c-item-list__ttl a")
        price_el = item.select_one("div.c-item-list__price")
        if not link_el:
            continue
        raw_name = link_el.get_text(strip=True)
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue
        href = link_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_match = re.search(r"([\d,]+)円", price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_status = detect_stock_status(raw_name)
        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    # cbidをまたいで重複する商品URLはここでまとめて除外する(実データでは
    # カテゴリ同士の重複は確認されていないが、保険として持たせる)
    items_by_url: dict[str, dict] = {}
    for cbid, category_hint in TARGET_CATEGORIES.items():
        page = 1
        while True:
            items = scrape_category_list_page(cbid, page)
            if not items:
                break
            for item in items:
                items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1], "manual")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_etop.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_etop.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
