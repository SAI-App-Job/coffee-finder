# -*- coding: utf-8 -*-
"""
scrape_roastdesign.py

Roast Design Coffee(roastdesigncoffee.com、カラーミーショップ/shop-pro.jp)の
商品詳細ページをパースする。神奈川県川崎市麻生区(新百合ヶ丘マプレ内)の本店に加え、
登戸・向ヶ丘遊園間に「B-side向ヶ丘遊園・登戸店」を構える2拠点展開のスペシャルティ
コーヒー専門自家焙煎店。

scrape_philocoffea.pyをテンプレートに実装しているが、同じshop-pro.jpでも
店舗が選んだテーマ(テンプレート)がPHILOCOFFEAとは異なり、HTML構造・CSSクラス名は
別物(実データ確認済み、2026-08時点)。共通しているのはURLクエリの体系
(?mode=srh / ?mode=grp&gid=N / ?page=N)と、`var Colorme = {...}` に埋め込まれた
商品JSON(name/sales_price_including_tax/stock_num等)のみ。

【一覧ページ】 ul.c-product-list > li.c-product-list__item。商品名とリンクは
同一の <a class="c-product-list__name" href="?pid=..."> にまとまっている
(PHILOCOFFEAは別要素だった)。ページネーションは?page=N。

【詳細ページ】 産地情報はdiv.seisannkoku > table(th/td形式、生産国/エリア/標高/
品種/生産処理/焙煎度/カッピングコメント等)に構造化されている。ただし
div.seisannkokuクラスは「配送方法・Q&A」のようなFAQテーブルにも使い回されて
いることが実データで判明したため、「生産国」キーが無いテーブルは無効(産地情報
ではない)とみなす。在庫はPHILOCOFFEAと違い`var Colorme`のproduct.stock_numに
構造化されており信頼できる(PHILOCOFFEAのようなコメントアウト問題は無い)。

【非コーヒー豆の除外】 gid=3128667(書籍、3件全て非コーヒー豆)・gid=2431639
(カフェラテベース、リキッド商品)をカテゴリごと除外。「コールドブリューパック」
(即飲み用に加工済みで生豆/粉としては売られていない)もPHILOCOFFEAの
NON_BEAN_KEYWORDS方針を踏襲してキーワード除外する。ギフトボックス(コーヒー
バッグ12個入り等、複数産地の詰め合わせで単一の産地情報を持たない商品)は、
カテゴリ除外ではなくPHILOCOFFEAと同じ「産地情報(表)も商品名からの産地国も
ブレンド判定も無ければ除外」という構造的なチェックに任せる(実データ確認済み:
ギフトボックス商品のdiv.seisannkokuテーブルには「生産国」キーが無く配送方法の
FAQのみだった一方、個別の【COFFEE BAG】商品は商品名に産地国名を含むため
このチェックで正しく残る)。

robots.txt確認済み(2026年8月時点): PHILOCOFFEAと同一の記述(User-agent: * は
/secure/と/cart/のみ制限、SEO分析系ボットは個別に全面禁止)。

【差分ベーススクレイピング】一覧ページ(軽量)の時点で商品名・価格・在庫状況が
前回(data/products.json)と変わっていない商品は、詳細ページの再取得をスキップ
して前回のレコードをそのまま使い回す(previous_data.py参照)。
"""

import json
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
    "name": "Roast Design Coffee",
    "url": "https://roastdesigncoffee.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県川崎市麻生区上麻生1-6-3 マプレGF階",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし。PHILOCOFFEAと同一の記述)",
}

CRAWL_DELAY_SECONDS = 3
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://roastdesigncoffee.com/"
LIST_BASE_URL = "https://roastdesigncoffee.com/?mode=srh&keyword=&sort=n"
CATEGORY_LIST_BASE_URL = "https://roastdesigncoffee.com/?mode=grp"

# 器具・グッズ・リキッド等、コーヒー豆ではない商品を含むカテゴリ(gid)。
# 実データ確認済み(2026-08時点)。
#   3128667「書籍」: 3件、全て書籍(コーヒー豆0件)
#   2431639「カフェラテベース」: 2件、全てリキッド状のカフェラテ濃縮液(コーヒー豆0件)
EXCLUDED_CATEGORY_GIDS = {
    3128667: "書籍",
    2431639: "カフェラテベース",
}

# 豆の形状ではない、あるいは別の加工形態の商品(実データ確認済み: gid=2431638
# 「便利なコーヒーバッグ」内に混在)。COLD BREW PACKは既に抽出済みの液体に
# 近い形態(40g小袋の即席パック)で生豆/粉としては売られていないため、
# PHILOCOFFEAの「コールドブリューバッグ」除外方針を踏襲する。
NON_BEAN_KEYWORDS = ["コールドブリュー", "COLD BREW", "カフェラテベース", "カフェオレベース"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
LIST_PRICE_PATTERN = re.compile(r"^([\d,]+)円")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*(?:-|~|〜)\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    """`var Colorme = {...}` に埋め込まれた商品JSON(product部分)を取得する。
    name/stock_num/sales_price_including_taxが構造化されており、PHILOCOFFEAの
    ように一覧ページの品切れ表示がコメントアウトされている問題が無い、
    信頼できる一次情報。見つからない/パースできない場合はNoneを返す。"""
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


def parse_origin_table(soup: BeautifulSoup) -> dict:
    """div.seisannkoku > table(th/td形式)から産地情報をキーバリュー抽出する。

    実データ調査で判明: div.seisannkokuというクラス名は産地情報テーブル専用
    ではなく、「配送方法・Q&A」(配送方法/送料/賞味期限等)のようなFAQテーブルにも
    使い回されている(複数商品の詰め合わせギフトボックス等で確認)。「生産国」
    キーの有無で本物の産地情報テーブルかどうかを判定し、無ければ空辞書を返す
    (=このテーブルは産地情報として扱わない)。
    """
    table = soup.select_one("div.seisannkoku table")
    if not table:
        return {}

    raw = {}
    for tr in table.select("tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            value = td.get_text()
            value = re.sub(r"\n+", ", ", value)
            value = re.sub(r",\s*,", ",", value)
            value = re.sub(r"\s{2,}", " ", value).strip(" ,")
            raw[th.get_text(strip=True)] = value

    if "生産国" not in raw:
        return {}
    return raw


def parse_product_detail(url: str) -> dict:
    """商品詳細ページ1件をパースする。

    フレーバーコーヒーは他の解析より先に判定し、該当する場合は
    産地等の詳細解析を行わない(coffee_parser.pyの方針を踏襲)。
    """
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)

    raw_name = ""
    price = None
    structural_out_of_stock = False
    if colorme_product:
        raw_name = colorme_product.get("name", "")
        price = colorme_product.get("sales_price_including_tax")
        stock_num = colorme_product.get("stock_num")
        structural_out_of_stock = isinstance(stock_num, int) and stock_num <= 0
    if not raw_name:
        # フォールバック: JSON構造が変わった場合のみHTML側の要素名から取得
        name_el = soup.select_one("div.p-cart-form__name")
        raw_name = name_el.get_text(strip=True) if name_el else ""

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

    origin_table = parse_origin_table(soup)

    # 産地情報の表(生産国キーを持つ本物のもの)、商品名から解析できる産地国、
    # ブレンド判定のいずれも存在しない場合のみ、コーヒー豆商品ではない
    # (ギフトボックス等の詰め合わせ商品)とみなして除外する。
    # カテゴリ除外(EXCLUDED_CATEGORY_GIDS)をすり抜けた商品や、今後追加
    # される未知の器具・グッズに対する保険的なチェック(PHILOCOFFEAと同じ方針)。
    # 実データ確認済み: 「コーヒーバッグ ギフトボックス(12個入り)」等の詰め
    # 合わせ商品はdiv.seisannkokuに配送方法のFAQテーブルしか持たず(=生産国
    # キー無し)、商品名にも産地国名を含まないため、このチェックで正しく除外
    # される一方、「【COFFEE BAG】ロン グアテマラ サンタクルス 1個」のような
    # 単品コーヒーバッグは商品名に産地国名を含むため除外されない。
    if (
        not origin_table
        and not parsed.get("origin_country")
        and parsed.get("category") != "ブレンド"
    ):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "non_bean": True,
            "stock_status": stock_status,
            "product_url": url,
        }

    # 産地情報の表は商品名パースより確実な一次情報として優先的に反映する
    if origin_table.get("生産国"):
        country = detect_country_name(origin_table["生産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    if origin_table.get("生産処理"):
        parsed["processing_method"] = normalize_processing_method(origin_table["生産処理"])

    altitude_min, altitude_max = None, None
    altitude_raw = origin_table.get("標高")
    if altitude_raw:
        range_m = ALTITUDE_RANGE_PATTERN.search(altitude_raw)
        if range_m:
            altitude_min = int(range_m.group(1).replace(",", ""))
            altitude_max = int(range_m.group(2).replace(",", ""))
        else:
            single_m = ALTITUDE_SINGLE_PATTERN.search(altitude_raw)
            if single_m:
                altitude_min = altitude_max = int(single_m.group(1).replace(",", ""))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],  # 商品名からの8段階判定(取れないことが多い)
        "roast_hint": origin_table.get("焙煎度"),  # 「浅煎り/中煎り/深煎り」の簡易表記(参考表示)
        "roast_selectable": False,  # 挽き方は選べるが焙煎度自体の選択肢は確認できず
        "post_processing_tags": parsed["post_processing_tags"],
        "producer_name": origin_table.get("生産者"),
        # 「農園」または「ウェットミル」(ケニア等、農園単位ではなく共同水洗場
        # 単位で扱う産地で使われるキー。PHILOCOFFEAの「WS」に相当)
        "farm_name": origin_table.get("農園") or origin_table.get("ウェットミル"),
        "region_detail": origin_table.get("エリア"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "variety": origin_table.get("品種"),
        "flavor_notes": origin_table.get("カッピングコメント"),
        "blend_components": [],  # 実データではブレンド商品・複数産地表の例が見つからず未対応
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.c-product-list__item")

    results = []
    for item in items:
        # 商品名とリンクは同一の<a class="c-product-list__name">にまとまっている
        # (PHILOCOFFEAは別要素だったが、このテーマでは統合されている)
        name_link_el = item.select_one("a.c-product-list__name")
        price_el = item.select_one("div.c-product-list__price")

        if not name_link_el:
            continue

        raw_name = name_link_el.get_text(strip=True)
        href = name_link_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_text = price_el.get_text(strip=True)
            price_match = LIST_PRICE_PATTERN.search(price_text)
            if price_match:
                price = int(price_match.group(1).replace(",", ""))

        # 一覧ページには品切れ表示要素が見当たらない(実データ確認済み)。
        # 構造化された在庫数(stock_num)は詳細ページのJSONにしかないため、
        # 一覧段階では商品名テキストのみで在庫状態を判定する。
        stock_status = detect_stock_status(raw_name)

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
        })
    return results


def scrape_excluded_category_urls() -> set[str]:
    """EXCLUDED_CATEGORY_GIDSに列挙したカテゴリ(書籍・カフェラテベース等)の
    商品URLを集める。PHILOCOFFEAと同じ方式(サイト内検索結果から差し引く)。"""
    excluded_urls: set[str] = set()
    for gid, category_name in EXCLUDED_CATEGORY_GIDS.items():
        page = 1
        count = 0
        while True:
            url = f"{CATEGORY_LIST_BASE_URL}&gid={gid}"
            if page > 1:
                url += f"&page={page}"
            soup = fetch_page(url)
            items = soup.select("li.c-product-list__item")
            if not items:
                break
            for item in items:
                link = item.select_one("a.c-product-list__name")
                if not link:
                    continue
                href = link.get("href", "")
                product_url = f"{BASE_URL}{href}" if href.startswith("?") else href
                excluded_urls.add(product_url)
                count += 1
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)
        print(f"[info] 除外カテゴリ「{category_name}」(gid={gid}): {count}件")
    return excluded_urls


def scrape_all_products(fetch_details: bool = True, max_pages: int = 50) -> tuple[list[dict], list[dict], list[dict]]:
    """一覧ページを全ページ辿り、各商品の詳細ページもパースして結合する。

    戻り値は (products, flavored_products, non_bean_products) のタプル。
    フレーバーコーヒー・別の加工形態の商品(コールドブリューパック等)・
    コーヒー豆ではない商品(書籍・ギフトボックス等)はいずれも本体のproductsに
    含めない。
    """
    excluded_urls = scrape_excluded_category_urls()

    all_list_items = []
    for page in range(1, max_pages + 1):
        items = scrape_product_list_page(page)
        if not items:
            break
        items = [i for i in items if not any(kw in i["raw_name"] for kw in NON_BEAN_KEYWORDS)]
        items = [i for i in items if i["product_url"] not in excluded_urls]
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
            detail["out_of_stock"] = detail["stock_status"] != "販売中"
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
        with open("data_roastdesign.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_roastdesign.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
