# -*- coding: utf-8 -*-
"""
scrape_chouette.py

chouette torréfacteur laboratoire(chouettetl.theshop.jp、東京都世田谷区)の
商品情報を取得する。NAGI COFFEE(scrape_nagi.py)・FINETIME COFFEE ROASTERS
(scrape_finetime.py)と同じTHE SHOP(BASE系)プラットフォームだが、実データ
確認の結果それらとは異なる「Relation」テーマが使われており、商品詳細ページに
schema.org JSON-LD構造化データが一切埋め込まれていないことが判明した(2026-08
確認)。itemDescription(商品説明文)も全商品共通の寄付プログラム
(【chouette blanche】)の定型文のみで、産地・精選方法等の個別情報を一切含まない。
そのため本スクレイパーは、他のTHE SHOP系スクレイパーと異なりJSON-LD/説明文の
パースを行わず、商品名(一覧ページのcard-title、詳細ページのh1.itemTitleと同一)
のみをcoffee_parser.parse_product()で解析する、より単純な構成になっている。

robots.txt確認済み(2026-08時点): NAGI COFFEE・FINETIME COFFEE ROASTERSと同一の
記述(curl/python-requests/aiohttp等の一般的なHTTPクライアントは個別に
Disallow: /指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・
/api/shops/・違反報告ページ以外はAllow: /)。本スクレイパーが使用する商品詳細
ページ(/items/)・カテゴリ一覧ページ(/categories/)はいずれもDisallow対象に
含まれない。

【カテゴリ構成と対象範囲について】
「コーヒー豆」(親カテゴリ、id=1372434)配下に「Grand Reserve」「Premium
experience」「Special selection」「Classic」「Decaf」という5つの品質ライン別
サブカテゴリと、「定期便」「コーヒー生豆」「コーヒーツール」(カリタ/ハリオ/
ボダム等のブランド別サブカテゴリを含む)・「セミナー＆ワークショップ」・
「プレゼント」・「グッズ」という非対象カテゴリが並列している。実データ調査の
結果、親カテゴリ(コーヒー豆)のページ自体が5つのライン別サブカテゴリの商品を
すべて含む上位集合になっている(かつ、いずれのサブカテゴリにも属さない
非コーヒー豆商品が2件含まれる)ことを確認した。よって本スクレイパーは
親カテゴリ(1372434)のみをクロールする(ページネーション無し、全19件が
1ページに収まることも確認済み)。

【豆売り商品以外の除外について】
親カテゴリの19件中、以下の8件は特定の一豆を指す商品ではないため除外する
(NON_BEAN_KEYWORDS参照、実データ確認済み):
  - 【初めての方限定】テイスティングセット送料無料(お試しセット)
  - あなたのスタンダードになる - The Essential Coffee
    (実データ確認済み: 商品オプション「The Essential Coffee」がClassic/
    Special selection/Premium experience/Reserveの4ラインから1つを選び、
    「おまかせ」で豆が決まるアソート商品。特定の一豆を指定できないため除外)
  - 【5p/cセット】コーヒーバッグ　ディップスタイル(ドリップバッグ)
  - "送料無料" コーヒーバッグ定期便　10p/c + おまけ1p/c(定期便)
  - 【初月のみ】おまかせ定期便　S/M/Lサイズパッケージ(定期便、3件)
  - 【chouette blanche】白いフクロウの定期便(定期便)
残り11件が実際の特定の豆を指す商品(ストレート10件+デカフェ1件)。

【重量表記について】
実データ確認済み: 対象11件のうち10件は商品名末尾に半角「100g」の表記があるが、
「デカフェ・カフェインレス　Décaf Ethiopia Mountain Water Process 100g Dark
roast」の1件のみ、重量の後ろにさらに焙煎度の英語表記が続き、末尾には来ない。
そのため重量は商品名の末尾ではなく、商品名中のどこかにある最初の「数字+g」
パターンとして抽出する(WEIGHT_PATTERN参照)。

【焙煎度について】
上記デカフェ商品にのみ「Dark roast」という英語の焙煎度表記があるが、
coffee_parser.ROAST_KEYWORDSはプロ向け8段階(ライト〜イタリアン)の日本語表記
のみに対応しており、この英語の粗い表記(Light/Medium/Dark等)はマッチしない。
他店舗と同じ方針(粗い表記はroast_levelではなくroast_hintに保持)に従い、
ENGLISH_ROAST_HINT_PATTERNで検出しroast_hintに保持する。

【カテゴリヒント(category_hint)について】
実データ確認済み: 商品名先頭の【Grand Reserve】等のブランド表記は、その商品が
実際に属するサブカテゴリ(ライン)と完全に一致していた(唯一の例外「Tanzania
Acacia Hills Kent AA Honey 100g」はブランド表記が商品名に無いが、実際には
Special selectionサブカテゴリに属することをサブカテゴリページのクロールで
確認済み)。ただしこれらのライン名は国名を含まないため、
apply_category_hint_fallback()による産地補完には寄与しない(あくまで参考表示用)。
商品名の【】表記のみから抽出し、表記が無い場合はcategory_hintをNoneのままにする
(1件のみの例外のために追加のサブカテゴリクロールを行うコストに見合わないと判断)。

【在庫状態について】
実データ確認済み(2026-08時点): 商品詳細ページに<div id="stockStatus"
class="stockStatus hasStock">という要素があり、在庫があるとhasStockクラスが
付与される(実データで売り切れ商品の実例は確認できなかったため、hasStock
クラスが無い場合を構造的な品切れシグナルとして扱う設計としている)。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "chouette torréfacteur laboratoire",
    "url": "https://chouettetl.theshop.jp/",
    "platform": "THE SHOP(BASE系)",
    "address": "東京都世田谷区宮坂1-39-11",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-08確認。NAGI COFFEE・FINETIME COFFEE ROASTERSと同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://chouettetl.theshop.jp"
# 理由はモジュールdocstring参照(親カテゴリが5ラインのサブカテゴリを包含する上位集合)
CATEGORY_ID = "1372434"  # コーヒー豆
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(特定の一豆を指さない商品を除外)
NON_BEAN_KEYWORDS = ["テイスティングセット", "定期便", "コーヒーバッグ", "Essential Coffee"]

TITLE_TAG_PATTERN = re.compile(r"^【(.+?)】")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ENGLISH_ROAST_HINT_PATTERN = re.compile(r"(?:Light|Medium[- ]?Dark|Medium|Dark|City|Full City)\s*[Rr]oast")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight(title: str) -> int | None:
    text = unicodedata.normalize("NFKC", title or "")
    m = WEIGHT_PATTERN.search(text)
    return int(m.group(1)) if m else None


def parse_category_hint(title: str) -> str | None:
    m = TITLE_TAG_PATTERN.match(title)
    return m.group(1).strip() if m else None


def parse_roast_hint(title: str) -> str | None:
    m = ENGLISH_ROAST_HINT_PATTERN.search(title)
    return m.group(0).strip() if m else None


def build_record(product_url: str, title: str, price: int | None, structural_out_of_stock: bool) -> dict:
    parsed = parse_product(title)

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

    parsed = apply_category_hint_fallback(parsed, parse_category_hint(title))
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": parse_category_hint(title),
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_hint": parse_roast_hint(title),
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, title: str, price: int | None) -> dict:
    soup = fetch_page(url)
    title_el = soup.select_one("h1.itemTitle")
    if not title_el:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": url,
        }

    stock_el = soup.select_one("div.stockStatus")
    structural_out_of_stock = bool(stock_el) and "hasStock" not in (stock_el.get("class") or [])

    return build_record(url, title_el.get_text(strip=True), price, structural_out_of_stock)


def scrape_category_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{CATEGORY_ID}")
    results = []
    seen_urls = set()
    for card in soup.select("div.card"):
        link_el = card.select_one('a[href*="/items/"]')
        title_el = card.select_one("h4.card-title")
        if not link_el or not title_el:
            continue
        raw_name = title_el.get_text(strip=True)
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        price = None
        price_el = card.select_one("span.item-price")
        if price_el:
            m = re.search(r"([\d,]+)", price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        results.append({"raw_name": raw_name, "product_url": product_url, "price": price})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items = scrape_category_list()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"], price=item["price"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(item["product_url"], item["raw_name"], item["price"])
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
        result = parse_product_detail(sys.argv[1], "", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_chouette.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_chouette.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
