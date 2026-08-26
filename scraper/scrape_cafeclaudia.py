# -*- coding: utf-8 -*-
"""
scrape_cafeclaudia.py

カフェクラウディア(cafeclaudia.com、神奈川県小田原市中町)の商品情報を取得する。
オンラインストアはBASE(cafeclaudia.official.ec)。本コードベース初のBASE実装
(explore_candidate.pyのPLATFORM_FINGERPRINTSでは従来「未対応。構造調査が必要。」)。

【稼働ストアの確認について】実データ確認済み(2026-08時点):
カフェクラウディアには過去カラーミーショップ(cafeclaudia.shop-pro.jp)とBASE
(cafeclaudia.official.ec)の2つのオンラインストアURLが公式サイトに掲載されて
いたが、cafeclaudia.shop-pro.jp は302リダイレクトの先が
`https://err.shop-pro.jp/404.htm`(カラーミーショップ自体の共通404ページ、
タイトルも「お探しのページは見つかりませんでした」)であり、閉店済みで実体が
無いことを確認した。一方cafeclaudia.official.ecは200 OKで実際に25件の商品
一覧・購入導線(カート追加ボタン、在庫数)が生きている。よって稼働している
BASEストアのみを対象に実装する。

robots.txt確認済み(2026-08時点): curl・python-requests・aiohttp・
Go-http-client等の匿名UAは名指しで全面Disallowされている(BASE標準のボット
対策)が、本スクレイパーは独自のUser-Agent(CoffeeFinderBot/0.1)を使うため
名指しリストには該当せず、「User-agent: *」ブロック(Allow: /、
/cart/・/web_cart/・/shops/・/en/shops/・/api/shops/・/illegal_reports/のみ
Disallow)が適用され、商品ページ・カテゴリページの取得は許可されている。

【カテゴリ構成について】実データ確認済み(2026-08時点):
「コーヒー」(親, id=4723284)配下に「コーヒー豆」(id=4723287、対象)・
「ドリップバッグ」(id=4723289、対象外)・「ディップコーヒー」(id=4723291、
対象外)の3小カテゴリがあり、「コーヒーセット」(id=4757806)・「グッズ」
(id=5599067)・「その他」(id=6974668)が別途トップレベルに存在する。豆売り
商品は「コーヒー豆」カテゴリのみで網羅できる(全25件・2ページ、実データ
確認済み。`?page=N`のクエリパラメータでページ送りし、空になったら終端)。
ただしこのカテゴリ内にも「【送料無料】店主のおまかせコーヒー豆400g
(100g×4)」のような複数銘柄をランダムに詰め合わせる「おまかせ」商品、
ギフトセット、「ドリップオンコーヒーバラエティパック15個入り」「ディップ
スタイルコーヒーバラエティパック15個入り」のような豆売りではない詰め合わせ、
さらには「カフェクラウディア10周年記念CD テーマソング「クラウディアへいこう」」
というコーヒーとは無関係な記念CD商品まで混在していたため(実データ確認済み、
初回実行後にdata/products.jsonを確認して発覚)、商品名に「セット」「おまかせ」
「バラエティパック」「記念CD」のいずれかを含む商品は除外する。

【商品ページの構造について】
JSON-LD・構造化テーブルは無く、価格は`<div id="price"><p>¥3,800</p></div>`、
産地・農園・品種等はすべて商品名(例:「パナマ ドン・ジュリアン農園「プライド
オブ パカマラ」ナチュラル / 100g」)から読み取る(説明文は農園のストーリー等
長い読み物調で構造化キー抽出に向かない。Coulaneと同じ判断で、flavor_notesは
確実な情報源が無いためnullのままとする)。重量は商品名末尾の「100g」
「100ｇ」(半角/全角g)表記から取得する。

【グラインドサイズ選択について】
商品詳細ページには「種類」という名前のセレクトボックスがあるが、これは
焙煎度ではなく挽き方(豆のまま/粗挽き/中挽き/中細挽き/細挽き/極細挽き)の
選択で、焙煎度自体は商品ごとに固定(タイトルに「(ミディアムロースト)」等の
形で明記される場合とされない場合がある)。roast_selectableを誤ってTrueに
しないよう、この店舗では常にFalseを明示する(aggregate_shops.pyのデフォルト
推定ロジックはroast_level無し・ストレートの場合Trueと推定してしまうため)。

【在庫判定・差分スクレイピングを行わない理由について】
実データ確認済み: 挽き方セレクトの各<option>に`data-stock="N"`属性があり、
店舗側のJSが在庫0の場合に「カートに入れる」ボタンを隠し「SOLD OUT」表示に
切り替える仕組みになっている。挽き方のいずれか1つでも在庫がある場合は
購入可能なため、data-stockの最大値で在庫有無を判定する。ただしこの在庫情報は
商品詳細ページにしか無く一覧ページには出ないため、他店舗のような
「一覧の価格・在庫が前回と同じなら詳細取得をスキップする」差分方式では
在庫切れへの変化(価格・商品名が変わらないまま在庫だけ0になるケース)を
検出できなくなってしまう。全25件と小規模で負荷も軽微なため、この店舗のみ
差分スキップを行わず毎回全件の詳細ページを取得し、正確性を優先する。

【中国産の検出について】
実データ確認済み: 「中国 雲南 プーアル トリプルファーメンテーションナチュラル」
という中国産商品があったが、coffee_parser.pyのORIGIN_COUNTRY_KEYWORDSには
「中国」自体が未登録だった(「タイ」と同様、「中国地方」という日本国内の
地方名との衝突リスクがあるマスタ側への追加は見送り、この店舗のスクレイパー
内でのみ「雲南」という誤爆リスクの低い地域名をトリガーに中国産と判定する
ローカルなフォールバックを実装している)。

【グレード表記の追加対応について】
実データ確認済み: 「エチオピア ベンチ・マジG-1」「エチオピア グジG-1」のように
ハイフン付きの「G-1」表記が見つかった。coffee_parser.pyのGRADE_PATTERNは
従来ハイフン無し(G1)のみに対応していたため、ハイフン有無どちらにもマッチし
G1表記へ正規化するよう修正済み(coffee_parser.py側の変更、本タスクで実施)。
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
    VARIETY_KEYWORDS,
)

SHOP_INFO = {
    "name": "カフェクラウディア",
    "url": "https://cafeclaudia.official.ec/",
    "platform": "BASE",
    "address": "神奈川県小田原市中町1-15-1 ホワイトシャトル102号",
    "prefecture": "神奈川県",
    "robots_txt_status": (
        "許可(2026-08確認。curl/python-requests等の匿名UAは名指しで全面禁止だが、"
        "独自User-Agent(CoffeeFinderBot)は「User-agent: *」規定の対象となり、"
        "/cart/・/web_cart/・/shops/・/api/shops/等以外は許可)"
    ),
}

BASE_URL = "https://cafeclaudia.official.ec"
BEAN_CATEGORY_ID = 4723287  # コーヒー豆(実データ確認済み: 豆売りはこのカテゴリのみ)
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): User-agent:*にCrawl-delay指定なし
# (Bingbotにのみ300秒指定があるが、名指しのBingbot以外には適用されない)
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

EXCLUDE_TITLE_KEYWORDS = ["セット", "おまかせ", "バラエティパック", "記念CD"]

PRICE_PATTERN = re.compile(r'id="price">\s*<p>[¥￥]([\d,]+)\s*</p>')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
STOCK_PATTERN = re.compile(r'data-stock="(\d+)"')
FARM_NAME_PATTERN = re.compile(r"([^\s　]{2,20}(?:農園|組合))")
DECAF_PROCESS_NAME_PATTERN = re.compile(r"(マウンテンウォータープロセス)")


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup, resp.text


def detect_decaf_process(title: str) -> str | None:
    if "カフェインレス" not in title and "デカフェ" not in title:
        return None
    m = DECAF_PROCESS_NAME_PATTERN.search(title)
    if m:
        return f"{m.group(1)}によりカフェインを除去"
    return "デカフェ(除去方法の詳細記載なし)"


def parse_product_detail(url: str) -> dict:
    soup, html_text = fetch_page(url)

    title_el = soup.select_one("h1.itemTitle")
    raw_name = title_el.get_text(strip=True) if title_el else ""

    price_match = PRICE_PATTERN.search(html_text)
    price = int(price_match.group(1).replace(",", "")) if price_match else None

    weight_match = WEIGHT_PATTERN.search(raw_name)
    weight_g = int(weight_match.group(1)) if weight_match else None

    stock_values = [int(v) for v in STOCK_PATTERN.findall(html_text)]
    structural_out_of_stock = bool(stock_values) and max(stock_values) <= 0
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

    farm_match = FARM_NAME_PATTERN.search(raw_name)
    farm_name = farm_match.group(1) if farm_match else None

    variety = None
    for kw, normalized in VARIETY_KEYWORDS.items():
        if kw in raw_name:
            variety = normalized
            break

    parsed = apply_category_hint_fallback(parsed, None)

    if not parsed["origin_country"] and "雲南" in raw_name:
        # 「中国」自体はcoffee_parser.py共通のORIGIN_COUNTRY_KEYWORDSに未登録
        # (モジュール冒頭docstring参照)。この店舗のローカルフォールバックとして、
        # 誤爆リスクの低い「雲南」(中国産コーヒーの主要産地名)をトリガーにする。
        parsed["origin_country"] = "中国"
        parsed["origin_source"] = "region_name"

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "roast_selectable": False,  # 実データ確認済み: セレクトは挽き方のみで焙煎度選択は無い
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_name": farm_name,
        "variety": variety,
        "decaf_process": detect_decaf_process(raw_name),
        "weight_g": weight_g,
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


def is_target_title(raw_name: str) -> bool:
    return not any(kw in raw_name for kw in EXCLUDE_TITLE_KEYWORDS)


def scrape_category_list_page(page: int) -> list[dict]:
    url = f"{BASE_URL}/categories/{BEAN_CATEGORY_ID}"
    if page > 1:
        url += f"?page={page}"
    soup, _ = fetch_page(url)

    results = []
    seen_urls = set()
    for card in soup.select("div.card"):
        link = card.select_one('a[href*="/items/"]')
        title_el = card.select_one(".card-title")
        if not link or not title_el:
            continue
        href = link.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"product_url": product_url, "raw_name": title_el.get_text(strip=True)})
    return results


def scrape_all_products(max_pages: int = 20) -> tuple[list[dict], list[dict]]:
    """コーヒー豆カテゴリを全ページ辿り、除外対象(セット・おまかせ)を除いた
    各商品の詳細ページを取得する。差分スキップを行わない理由はモジュール
    冒頭のdocstring参照。戻り値は (products, flavored_products) のタプル。
    """
    all_items = []
    seen_urls = set()
    for page in range(1, max_pages + 1):
        items = scrape_category_list_page(page)
        if not items:
            break
        for item in items:
            if item["product_url"] in seen_urls:
                continue
            seen_urls.add(item["product_url"])
            if is_target_title(item["raw_name"]):
                all_items.append(item)
        time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    flavored_records = []
    for item in all_items:
        try:
            detail = parse_product_detail(item["product_url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        # 一覧カードのタイトル(card-title)と詳細ページのタイトル(h1.itemTitle)が
        # 万一食い違う場合に備え、詳細取得後にも除外判定をかけ直す(二重チェック)
        if not is_target_title(detail["raw_name"]):
            continue
        detail["out_of_stock"] = detail.get("stock_status", "販売中") != "販売中"
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_cafeclaudia.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_cafeclaudia.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
