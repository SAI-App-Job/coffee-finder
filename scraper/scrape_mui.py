# -*- coding: utf-8 -*-
"""
scrape_mui.py

Mui(mui-motosumi.co.jp、川崎市中原区木月)の商品詳細ページをパースする。
ShopServe(ショップサーブ)というこのプロジェクト初対応のプラットフォーム。

robots.txt確認済み(2026-08時点): mui-motosumi.co.jp・www.mui-motosumi.co.jp
どちらもrobots.txt自体が存在しない(404)。これは実質全面許可とみなせる
(explore_candidate.pyのcheck_robots_txt()と同じ解釈)。

【ShopServeの構造】実データ確認済み(2026-08時点、ET-IT01・BL-CY001等の実商品で確認):
- 商品一覧: `/SHOP/<カテゴリID>/t02/list<N>.html`(GETでページ送り可能。ページ番号を
  1つずつ増やし、section.column4が0件になったら終端とみなす)。「コーヒー豆一覧」
  カテゴリ(m=383792)がストレート・ブレンドの全商品を含む唯一のカテゴリで、これ以外
  (おすすめ/苦み少なめ等)は同じ商品の重複ビューのため対象にしない。
- 商品詳細ページに`gtag('event', 'view_item', {...})`という埋め込みJSがあり、
  税込価格(price)と、焙煎度合・産地(シングルオリジン/ブレンド)を含む詳細な
  カテゴリタグ(item_category)を構造化データとして取得できる(PHILOCOFFEAの
  `var Colorme = {...}`と同じ発想)。
- 単一原産地の商品のみ、「生産者＆産地情報」セクションに`table.info-table`
  (国名/地域/生産者/精製工場/オーナー/標高/品種/精製、デカフェ商品のみ
  デカフェ処理も追加)というth/td形式の表を持つ。ブレンド商品にはこの表が
  存在しない(実データ確認済み: BL-CY001で不在を確認)。PHILOCOFFEAのBEANS DATA表と
  同じ発想で、これを一次情報として商品名パースの結果を補強・上書きする。

【対象外商品の絞り込みについて】
「コーヒー豆一覧」カテゴリには、ストレート・ブレンドの単品に混じって、福袋的な
飲み比べセット・ギフトセット・お試しセットが同居している(実データ確認済み、
2026-08時点で40件中8件)。これらはproduct_urlのIDパターン(セット系はDG-/GF-/TR-
プレフィックス)では一貫して判別できなかったが、商品名(h1)に必ず「セット」を
含むことを全件確認済みのため、PHILOCOFFEAのNON_BEAN_KEYWORDSと同じ考え方で
商品名ベースの除外を行う。
"""

import re
import time

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
    "name": "Mui",
    "url": "https://www.mui-motosumi.co.jp/",
    "platform": "ShopServe",
    "address": "神奈川県川崎市中原区木月3-13-2",
    "prefecture": "神奈川県",
    "robots_txt_status": "robots.txtなし(2026-08確認。mui-motosumi.co.jp・www.mui-motosumi.co.jp"
                          "どちらも404で存在しない。実質全面許可とみなせる)",
}

CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 「コーヒー豆一覧」カテゴリ(m=383792)。実データ確認済み(2026-08時点): ストレート・
# ブレンドの全商品(セット類含め40件)を網羅する唯一のカテゴリで、これ以外の
# カテゴリ(おすすめ/苦み少なめ・酸味少なめ/MUIのギフト等)は同じ商品の重複ビュー。
LIST_BASE_URL = "https://www.mui-motosumi.co.jp/SHOP/383792/t02/list{page}.html"

# 単品のコーヒー豆ではない飲み比べ・ギフト・お試しセット。実データ確認済み
# (2026-08時点、該当8件すべての商品名(h1)に「セット」が含まれることを確認)。
NON_BEAN_KEYWORDS = ["セット"]

# 商品詳細ページの `gtag('event', 'view_item', {...})` から税込価格・カテゴリタグを
# 取得する。キーが非クォートのJS object literalでJSONとして直接パースできないため、
# 対象フィールドだけを正規表現で直接抜き出す(1商品詳細ページにview_itemイベントは
# 1つしかないことを実データで確認済みのため、ブロック境界を厳密に取らなくても
# 誤検出しない)。
GTAG_PRICE_PATTERN = re.compile(r"\bprice:\s*(\d+)")
GTAG_CATEGORY_PATTERN = re.compile(r'item_category:\s*"([^"]*)"')

# 一覧ページの価格表示は「¥2,200(税込 ¥2,376)」のように税抜・税込が併記される。
# PHILOCOFFEAと同じ理由(税込のみ抽出しないと桁違いの誤った値になる)で税込側を狙う。
LIST_PRICE_TAX_INCLUDED_PATTERN = re.compile(r"税込\s*¥\s*([\d,]+)")
LIST_STOCK_COUNT_PATTERN = re.compile(r"在庫\s*(\d+)\s*個")
DETAIL_STOCK_COUNT_PATTERN = re.compile(r"(\d+)\s*個")

WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")

# 「生産者＆産地情報」のtable.info-table(th/td形式)のキー名 → 内部フィールド名の対応。
INFO_TABLE_FIELD_MAP = {
    "国名": "country_raw",
    "地域": "region_detail",
    "生産者": "producer_name",
    "精製工場": "processing_plant",
    "オーナー": "owner",
    "標高": "altitude_raw",
    "品種": "variety",
    "精製": "processing_method_raw",
    "デカフェ処理": "decaf_process",
}

# 「標高」は「2,400m」のような単一値と、他店舗で見られる「1,400-1,900m」のような
# 範囲値の両方に備える(Muiの実データはこれまで単一値のみ確認しているが、範囲値が
# 出てきた場合もmin/maxとして扱えるようにしておく)。
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*-\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def parse_info_table(soup: BeautifulSoup) -> dict:
    """「生産者＆産地情報」のtable.info-table(th/td形式)を汎用的にキーバリュー
    抽出する。単一原産地の商品にのみ存在し、ブレンド商品には存在しない
    (実データ確認済み)。キー名はINFO_TABLE_FIELD_MAPで店舗依存の日本語見出しから
    内部フィールド名へ変換する(マップに無い見出しは無視する)。
    """
    table = soup.select_one("table.info-table")
    if not table:
        return {}
    raw = {}
    for tr in table.select("tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            field = INFO_TABLE_FIELD_MAP.get(th.get_text(strip=True))
            if not field:
                continue
            value = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
            raw[field] = value
    return raw


def extract_price(soup: BeautifulSoup, html_text: str) -> int | None:
    """gtag('event', 'view_item', {...})の埋め込みJSにある税込価格(price)を
    優先的に使う。見つからない場合のみtable.priceのテキストからフォールバックする
    (税抜・税込併記のテキストは誤読の危険があるため最終手段扱い、PHILOCOFFEAと同じ方針)。
    """
    m = GTAG_PRICE_PATTERN.search(html_text)
    if m:
        return int(m.group(1))

    price_table = soup.select_one("table.price")
    if price_table:
        text = price_table.get_text()
        m2 = LIST_PRICE_TAX_INCLUDED_PATTERN.search(text)
        if m2:
            return int(m2.group(1).replace(",", ""))
    return None


def extract_stock_count(soup: BeautifulSoup) -> int | None:
    """table.spec内の「在庫:」行から在庫数を取得する。行自体が無い商品
    (在庫管理をしていない商品)の場合はNoneを返す(在庫切れとは扱わない)。"""
    spec_table = soup.select_one("table.spec")
    if not spec_table:
        return None
    for tr in spec_table.select("tr"):
        th = tr.select_one("th")
        if th and "在庫" in th.get_text():
            td = tr.select_one("td")
            if td:
                m = DETAIL_STOCK_COUNT_PATTERN.search(td.get_text())
                if m:
                    return int(m.group(1))
    return None


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    html_text = str(soup)

    h1_el = soup.select_one("h1")
    raw_name = h1_el.get_text(strip=True) if h1_el else ""

    # セット系商品は一覧段階(NON_BEAN_KEYWORDS)で除外しているはずだが、直接URLを
    # 指定して呼び出すケース(単体実行時のデバッグ等)への保険として詳細ページ側でも
    # 同じ判定を行う。
    if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "product_url": url,
        }

    price = extract_price(soup, html_text)

    category_match = GTAG_CATEGORY_PATTERN.search(html_text)
    category_tags = (
        [t.strip() for t in category_match.group(1).split(",") if t.strip()]
        if category_match
        else []
    )

    stock_count = extract_stock_count(soup)
    structural_out_of_stock = stock_count is not None and stock_count <= 0
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "stock_status": stock_status,
            "product_url": url,
        }

    info = parse_info_table(soup)

    # info-table(単一原産地のみ存在)が無く、商品名からもブレンド・産地のいずれも
    # 判定できない場合のみ、コーヒー豆商品ではない(想定外の器具・グッズ等)とみなす。
    # PHILOCOFFEAと同じ考え方の保険的セーフティネット。
    if not info and not parsed.get("origin_country") and parsed.get("category") != "ブレンド":
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "stock_status": stock_status,
            "product_url": url,
        }

    if info.get("country_raw"):
        country = detect_country_name(info["country_raw"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "structured_table"

    if info.get("processing_method_raw"):
        parsed["processing_method"] = normalize_processing_method(info["processing_method_raw"])

    altitude_min, altitude_max = None, None
    if info.get("altitude_raw"):
        range_m = ALTITUDE_RANGE_PATTERN.search(info["altitude_raw"])
        if range_m:
            altitude_min = int(range_m.group(1).replace(",", ""))
            altitude_max = int(range_m.group(2).replace(",", ""))
        else:
            single_m = ALTITUDE_SINGLE_PATTERN.search(info["altitude_raw"])
            if single_m:
                altitude_min = altitude_max = int(single_m.group(1).replace(",", ""))

    # 「精製工場」「オーナー」はPRODUCER_LOT相当の独立フィールドが用意されていない
    # ため、farm_name(farm_note合成時に「農園:」ラベルで使われる)にまとめて格納する。
    farm_name = None
    if info.get("processing_plant"):
        farm_name = info["processing_plant"]
        if info.get("owner"):
            farm_name = f"{farm_name}(オーナー: {info['owner']})"
    elif info.get("owner"):
        farm_name = f"オーナー: {info['owner']}"

    parsed = apply_category_hint_fallback(parsed, " ".join(category_tags))

    taste_el = soup.select_one("div.taste-text")
    flavor_notes = re.sub(r"\s+", " ", taste_el.get_text(" ", strip=True)).strip() if taste_el else None

    weight_g = None
    m = WEIGHT_PATTERN.search(raw_name)
    if m:
        weight_g = int(m.group(1))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "category_hint": category_tags,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "producer_name": info.get("producer_name"),
        "farm_name": farm_name,
        "region_detail": info.get("region_detail"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "variety": info.get("variety"),
        "decaf_process": info.get("decaf_process"),
        "flavor_notes": flavor_notes,
        "weight_g": weight_g,
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


# --- 一覧ページのクロール処理 -------------------------------------------------
# 実データ確認済み(2026-08時点): 商品ブロックはsection.column4の繰り返し。
# ページ送りは/SHOP/383792/t02/list<N>.html(N=1,2,3...)というGETアクセス可能な
# URLパターンで、末尾を超えたページ(section.column4が0件)を検出したら終端とみなす
# (実データで5ページ目が0件になることを確認済み)。


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL.format(page=page)
    soup = fetch_page(url)
    items = soup.select("section.column4")

    results = []
    for item in items:
        title_el = item.select_one("div.itemThumb-wrap-right h2 a")
        if not title_el:
            continue
        raw_name = title_el.get_text(strip=True)
        href = title_el.get("href", "")
        product_url = f"https://www.mui-motosumi.co.jp{href}" if href.startswith("/") else href

        price_el = item.select_one("p.price")
        price = None
        if price_el:
            price_match = LIST_PRICE_TAX_INCLUDED_PATTERN.search(price_el.get_text())
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        stock_el = item.select_one("p.sps-itemList-stockDisp")
        structural_out_of_stock = False
        if stock_el:
            stock_match = LIST_STOCK_COUNT_PATTERN.search(stock_el.get_text())
            if stock_match and int(stock_match.group(1)) <= 0:
                structural_out_of_stock = True

        stock_status = detect_stock_status(raw_name, structural_out_of_stock)

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
        })
    return results


def scrape_all_products(fetch_details: bool = True, max_pages: int = 30) -> tuple[list[dict], list[dict], list[dict]]:
    """一覧ページを全ページ辿り、各商品の詳細ページもパースして結合する。

    戻り値は (products, flavored_products, non_bean_products) のタプル。
    """
    all_list_items = []
    for page in range(1, max_pages + 1):
        items = scrape_product_list_page(page)
        if not items:
            break
        # 飲み比べ・ギフト・お試しセット等は一覧の時点で除外(NON_BEAN_KEYWORDS)
        items = [i for i in items if not any(kw in i["raw_name"] for kw in NON_BEAN_KEYWORDS)]
        all_list_items.extend(items)
        time.sleep(CRAWL_DELAY_SECONDS)

    if not fetch_details:
        return all_list_items, [], []

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in all_list_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price=item.get("price"),
            stock_status=item["stock_status"],
        ):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"])
            detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            if prev:
                records.append(prev)

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys
    import json

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
        with open("data_mui.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mui.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
