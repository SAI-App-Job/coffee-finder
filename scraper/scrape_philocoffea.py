# -*- coding: utf-8 -*-
"""
scrape_philocoffea.py

PHILOCOFFEA(philocoffea.com、カラーミーショップ/shop-pro.jp)の商品詳細ページを
パースする。World Brewers Cup優勝者(粕谷哲氏)が運営するスペシャルティコーヒー専門店。

【現状】商品詳細ページ・商品一覧ページとも構造を確認済み(2026-08時点)。

robots.txt確認済み(2026年8月時点): User-agent: * は /secure/ と /cart/ のみ制限
(商品ページは対象外)。SEO分析系ボット(AhrefsBot等)は個別に全面禁止。

特徴: 商品名の先頭にロット番号(例:「287 Ethiopia G4 Tade GG Natural Decaf」)が
付く命名規則。また「BEANS DATA」というth/td形式の表に、農園・生産者・エリア・
標高・品種・生産処理・焙煎度・味わいまで構造化されており、これまでの3店舗で
最も情報粒度が高い。正規表現よりも表の汎用キーバリュー抽出が確実なため、
その方式を採用している。

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
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "PHILOCOFFEA",
    "url": "https://philocoffea.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "千葉県",  # 詳細住所は要確認(電話番号047-460-9400から市外局番のみ判明)
    "prefecture": "千葉県",
    "robots_txt_status": "許可(2026-08確認。/secure/と/cart/以外は制限なし)",
}

CRAWL_DELAY_SECONDS = 3  # 他店舗同様のcourtesy設定を踏襲
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 器具・グッズ等、コーヒー豆ではない商品を含むカテゴリ(gid)。Denim bisの
# EXCLUDED_CATEGORIESと同じ考え方で、クロール対象から丸ごと除外する。
# gid=2805103は実データ確認済み(2026-08時点、31件): ドリッパー・ペーパー
# フィルター・ケトル・コーヒー関連書籍等。コーヒー豆は0件だった。
EXCLUDED_CATEGORY_GIDS = {
    2805103: "コーヒー器具",
}
CATEGORY_LIST_BASE_URL = "https://philocoffea.com/?mode=grp"

# 「BEANS DATA」表(新テンプレート)を持たない商品ページの一部は、単に
# コーヒー豆ではない(器具・グッズ)のではなく、古い終売コーヒー豆が旧テンプレート
# (表ではなく商品ストーリー内の自由記述ブロック)のまま残っているケースがある
# ことが実データで確認された(2026-08時点、457件中325件が終売表記で、その
# 多くが旧テンプレート)。旧テンプレートは「＜豆情報＞」という見出しで
# 農園・生産者等を記載しているため、これを第二の判定材料として使う。
LEGACY_BEAN_INFO_MARKER = "＜豆情報＞"

# BEANS DATAの表キー名 → 内部フィールド名の対応(店舗依存の日本語見出しを正規化)
BEANS_DATA_FIELD_MAP = {
    "農園": "farm_name",
    "生産者": "producer_name",
    "エリア": "region_detail",
    "標高": "altitude_raw",
    "品種": "variety",
    "生産処理": "processing_method_raw",
    "ディカフェ処理": "decaf_process",
    "味わい": "flavor_notes",
}

ALTITUDE_PATTERN = re.compile(r"([\d,]+)\s*-\s*([\d,]+)\s*m")

# 商品詳細ページに埋め込まれた `var Colorme = {...};` から価格を取る際のパターン。
# strong.price のテキスト(例:「3,100円(税込3,348円)」)は税抜・税込の2つの金額を
# 含んでおり、単純な数字抽出(digitのみ残す)だと両方の数字が連結されて
# 「31003348」のような誤った値になる不具合が実データで確認された。
# ページに埋め込まれた構造化データ(product.sales_price_including_tax)を
# 優先的に使うことでこれを回避する。
COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


def parse_beans_data_table(soup: BeautifulSoup) -> dict:
    """「BEANS DATA」表(th/td形式)を汎用的にキーバリュー抽出する。

    店舗独自の見出し(農園/生産者/エリア等)がそのままキーになるため、
    正規表現でのパースより確実。<br>を改行に変換した上で結合するので、
    複数行にわたる「味わい」欄も改行区切りで整形して保持する。
    """
    table = soup.select_one("table.product_description__table")
    if not table:
        return {}

    raw = {}
    for tr in table.select("tr"):
        th = tr.select_one("th")
        td = tr.select_one("td")
        if th and td:
            # <br>を改行に変換済みなので、改行・余分な空白を整理してカンマ区切りにする
            value = td.get_text()
            value = re.sub(r"\n+", ", ", value)
            value = re.sub(r",\s*,", ",", value)  # 改行直後にカンマがあった場合の重複を除去
            value = re.sub(r"\s{2,}", " ", value).strip(" ,")
            raw[th.get_text(strip=True)] = value
    return raw


def extract_price_including_tax(soup: BeautifulSoup) -> int | None:
    """`var Colorme = {...}` に埋め込まれた商品JSONから税込価格
    (product.sales_price_including_tax)を取得する。見つからない/パースできない
    場合はNoneを返す(呼び出し側でstrong.priceのテキストにフォールバックする)。"""
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product", {}).get("sales_price_including_tax")
    return None


def parse_product_detail(url: str) -> dict:
    """商品詳細ページ1件をパースする。

    フレーバーコーヒーは他の解析より先に判定し、該当する場合は
    産地等の詳細解析を行わない(coffee_parser.pyの方針を踏襲)。
    """
    soup = fetch_page(url)

    name_el = soup.select_one("h1#itemName")
    price_el = soup.select_one("strong.price")
    group_tag_els = soup.select("ul#groupTag a")

    raw_name = name_el.get_text(strip=True) if name_el else ""

    # 商品名に「終売」「完売」等の表記が一切無いまま品切れになるケースが
    # 実データ調査で確認された(例: 「World Champion Series」等の限定商品)。
    # このdiv要素は一覧ページのp.productList__soldOutと違い、コメントアウト
    # されておらず実際に機能している(在庫がある商品では要素自体が存在しない
    # ことを確認済み)ため、商品名テキストと合わせた第二のシグナルとして使う。
    sold_out_el = soup.select_one("div.sold_out")
    stock_status = detect_stock_status(raw_name, bool(sold_out_el))

    price = extract_price_including_tax(soup)
    if price is None and price_el:
        # フォールバック: 構造化データが見つからない場合のみテキストから推定
        # (税抜・税込が併記されていると誤った値になりうるので最終手段扱い)
        price_digits = re.sub(r"[^\d]", "", price_el.get_text(strip=True))
        price = int(price_digits) if price_digits else None

    group_tags = [a.get_text(strip=True) for a in group_tag_els]

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

    beans_data = parse_beans_data_table(soup)

    # 新テンプレートのBEANS DATA表、旧テンプレートの＜豆情報＞ブロック、
    # 商品名から解析できる産地国(parsed["origin_country"])、ブレンド判定
    # (parsed["category"] == "ブレンド")のいずれも存在しない場合のみ、
    # コーヒー豆商品ではない(器具・グッズ等)とみなして除外する。
    # カテゴリ除外(EXCLUDED_CATEGORY_GIDS)をすり抜けた商品や、今後追加
    # される未知の器具・グッズに対する保険的なチェック。
    # 産地国チェックが必要な理由: gid=3105307(コーヒーバッグ)の一部の
    # ギフト向け商品(例: 「296 Colombia La Roca Geisha Washed」)は、
    # BEANS DATA表も＜豆情報＞ブロックも持たないギフト訴求文のみの詳細
    # ページだが、商品名に産地国名を含む正規の単一産地コーヒー豆である
    # ため、これを産地国名だけで誤って除外しないようにする。
    # ブレンド判定が必要な理由: 「011 TOKYO BLEND」等の看板ブレンドは、
    # 単一農園・単一産地の情報を持たない(=複数産地の豆を配合した商品の
    # 性質上、BEANS DATA表・＜豆情報＞・単一産地国のいずれも本来存在
    # しない)ため、他の3シグナルだけでは正規のブレンド商品まで
    # 器具・グッズと誤って除外してしまうことが実データ調査で判明した。
    if (
        not beans_data
        and LEGACY_BEAN_INFO_MARKER not in soup.get_text()
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

    # BEANS DATAの表は商品名パースより確実な一次情報として優先的に反映する
    if beans_data.get("生産処理"):
        parsed["processing_method"] = normalize_processing_method(beans_data["生産処理"])

    altitude_min, altitude_max = None, None
    if beans_data.get("標高"):
        m = ALTITUDE_PATTERN.search(beans_data["標高"])
        if m:
            altitude_min = int(m.group(1).replace(",", ""))
            altitude_max = int(m.group(2).replace(",", ""))

    # カテゴリタグ(group_tags)を産地推定のフォールバックとしても利用
    parsed = apply_category_hint_fallback(parsed, " ".join(group_tags))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "category_hint": group_tags,  # 店舗が付与したタグ(焙煎度/産地/味わい等の分類)
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],  # 商品名からの8段階判定(取れないことが多い)
        "post_processing_tags": parsed["post_processing_tags"],
        # PRODUCER_LOT相当のフィールド(BEANS DATA表から取得)
        "producer_name": beans_data.get("生産者"),
        "farm_name": beans_data.get("農園"),
        "region_detail": beans_data.get("エリア"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "variety": beans_data.get("品種"),
        "decaf_process": beans_data.get("ディカフェ処理"),  # 新しい軸: カフェインレス処理方法
        "flavor_notes": beans_data.get("味わい"),  # 新しい軸: テイスティングノート
        "source_note": str(beans_data),
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


# --- 一覧ページのクロール処理 -------------------------------------------------
# 実データ確認済み(2026-08時点): 商品グリッドは ul#productList > li.productList__unit。
# ページネーションは ?mode=srh&keyword=&sort=n&page=N という素直なURLクエリ
# (全474件・48ページを確認)。
LIST_BASE_URL = "https://philocoffea.com/?mode=srh&keyword=&sort=n"

# 豆の形状ではない商品(リキッドコーヒー、ギフトセット等)は
# 産地・精選方法を論じる対象にならないため、商品名のキーワードで除外する
NON_BEAN_KEYWORDS = ["リキッドコーヒー", "アソートギフト", "コールドブリューバッグ", "COLD BREW BAG"]

# 一覧ページの価格表示も詳細ページ同様「3,100円(税込3,348円)」のように税抜・税込の
# 2つの金額が併記されている。税込側だけを取り出す(単純な数字抽出だと両方の数字が
# 連結され、桁違いの誤った値になってしまうため)。
LIST_PRICE_TAX_INCLUDED_PATTERN = re.compile(r"税込([\d,]+)円")


def scrape_product_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = soup.select("li.productList__unit")

    results = []
    for item in items:
        link = item.select_one('a[href*="?pid="]')
        name_el = item.select_one("div.productList__name")
        price_el = item.select_one("div.productList__price")
        tag_els = item.select("div.productList__tags span")

        if not (link and name_el):
            continue

        raw_name = name_el.get_text(strip=True)
        href = link.get("href", "")
        product_url = f"https://philocoffea.com/{href}" if href.startswith("?") else href

        price = None
        if price_el:
            price_text = price_el.get_text(strip=True)
            tax_included_match = LIST_PRICE_TAX_INCLUDED_PATTERN.search(price_text)
            if tax_included_match:
                price = int(tax_included_match.group(1).replace(",", ""))
            else:
                # フォールバック: 税込表記が見つからない場合(セール品等で書式が
                # 異なる可能性)は、これまで通り数字のみを抽出する
                price_digits = re.sub(r"[^\d]", "", price_text)
                price = int(price_digits) if price_digits else None

        # 一覧ページの品切れ表示要素(p.productList__soldOut)は実データ調査の
        # 結果、常にHTMLコメント内にしか存在せず(恐らくJS側で動的に表示する
        # 前提のテンプレートが、コメントアウトされたまま出荷されている)、
        # BeautifulSoupのタグ検索では絶対にヒットしないことが判明した。
        # PHILOCOFFEAは代わりに商品名へ「終売」「完売」等を明記する運用の
        # ため、構造化フラグに頼らず商品名テキストのみで在庫状態を判定する。
        stock_status = detect_stock_status(raw_name)

        results.append({
            "raw_name": raw_name,
            "product_url": product_url,
            "price": price,
            "tags": [t.get_text(strip=True) for t in tag_els],
            "stock_status": stock_status,
            "out_of_stock": stock_status != "販売中",
        })
    return results


def scrape_excluded_category_urls() -> set[str]:
    """EXCLUDED_CATEGORY_GIDSに列挙したカテゴリ(器具・グッズ等)の商品URLを集める。

    PHILOCOFFEAはDenim bisと異なり、カテゴリ単位ではなく全カテゴリ横断のサイト内
    検索(?mode=srh)で一覧を取得している。そのため、カテゴリ単位でクロールして
    除外するのではなく、除外対象カテゴリ(?mode=grp&gid=...)の商品URL一覧を別途
    取得し、サイト内検索結果からこの集合に含まれるものを差し引く方式で
    Denim bisのEXCLUDED_CATEGORIESと同じ効果を得る。
    """
    excluded_urls: set[str] = set()
    for gid, category_name in EXCLUDED_CATEGORY_GIDS.items():
        page = 1
        count = 0
        while True:
            url = f"{CATEGORY_LIST_BASE_URL}&gid={gid}"
            if page > 1:
                url += f"&page={page}"
            soup = fetch_page(url)
            items = soup.select("li.productList__unit")
            if not items:
                break
            for item in items:
                link = item.select_one('a[href*="?pid="]')
                if not link:
                    continue
                href = link.get("href", "")
                product_url = f"https://philocoffea.com/{href}" if href.startswith("?") else href
                excluded_urls.add(product_url)
                count += 1
            page += 1
            time.sleep(CRAWL_DELAY_SECONDS)
        print(f"[info] 除外カテゴリ「{category_name}」(gid={gid}): {count}件")
    return excluded_urls


def scrape_all_products(fetch_details: bool = True, max_pages: int = 50) -> tuple[list[dict], list[dict], list[dict]]:
    """一覧ページを全ページ辿り、各商品の詳細ページもパースして結合する。

    戻り値は (products, flavored_products, non_bean_products) のタプル。
    フレーバーコーヒー・非・豆形状の商品(リキッドコーヒー等)・コーヒー豆ではない
    商品(器具・グッズ等)はいずれも本体のproductsに含めない。
    """
    excluded_urls = scrape_excluded_category_urls()

    all_list_items = []
    for page in range(1, max_pages + 1):
        items = scrape_product_list_page(page)
        if not items:
            break
        # 豆の形状ではない商品は一覧の時点で除外
        items = [i for i in items if not any(kw in i["raw_name"] for kw in NON_BEAN_KEYWORDS)]
        # 器具・グッズ等、除外対象カテゴリの商品も一覧の時点で除外
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
            # stock_statusはparse_product_detail内で、商品名テキストに加え
            # 詳細ページのdiv.sold_out要素(実際に機能している構造化シグナル)
            # も踏まえて判定済み。ここではout_of_stockを一貫させるだけでよい。
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
        with open("data_philocoffea.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_philocoffea.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
