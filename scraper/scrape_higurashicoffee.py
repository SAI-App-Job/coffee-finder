# -*- coding: utf-8 -*-
"""
scrape_higurashicoffee.py

ヒグラシ珈琲(蜩珈琲、higurashi-coffee.com、兵庫県豊岡市千代田町1-5(駅通
本店)、1930年創業・自家焙煎豆のオンライン販売)の商品情報を取得する。
BiND(ウェブライフ社のホームページ作成サービス、robots.txt自体が存在しない
サイトビルダー)+ BiND Cart(bindcart.com、外部ECウィジェットSaaS)。
本プロジェクトで初めてのBiND Cart店舗。

【プラットフォームについて】
実データ確認済み: トップページのmetaタグ(bind-mobile-theme)およびrobots.txt
不在時の404ページ本文("BiND Cloud / WebLife Server")からBiNDであることを
確認した。商品詳細ページ自体の静的HTMLには価格情報が含まれておらず(JSで
動的に注入される)、Chrome DevTools相当のネットワークログで実際の取得元を
調査した結果、外部SaaS「BiND Cart」(bindcart.com)のJSONP API
(https://shops-api2.bindcart.com/pagep.php?...&method=ProductDetail&
args=a:1:{i:0;s:<len>:"<product_id>";})を直接HTTPで呼び出せば認証不要で
商品名・価格・重量(sale_text)・表示フラグ(display_flg)を取得できることを
確認した。商品詳細ページの静的HTMLには`data-product="<id>"`として商品IDが
埋め込まれているため、JS実行やヘッドレスブラウザは不要。BASE/カラーミー/
Shopify/Ocnk/WooCommerce/EC-CUBEのいずれにも該当しない新規プラットフォーム
だが、上記の理由により低リスクな抽出方法として実装する。

robots.txt確認済み(2026-09時点): higurashi-coffee.com・shops-api2.bindcart.com
ともにrobots.txt自体が存在しない(404)。User-agent別の制限記述が一切ないため、
実質的にクロール制限なしと判断した。

【店名・住所について】
候補リストでは「豊岡市、2 locations (駅通本店・戸牧店)」だったが、公式
サイト内の店舗案内(pg372.html)で確認したところ、本店(オンラインショップの
運営元)の住所は候補リストの「駅通本店 〒668-0032 豊岡市千代田町1-5」と
一致することを確認した。焙煎(自家焙煎)を行っていることも同ページ・トップ
ページのmeta descriptionで確認済み。

【商品一覧の取得方法について】
実データ確認済み: オンラインショップの商品カテゴリのうち「コーヒー豆
（ブレンド）」(blendcoffee/pg97.html、9銘柄)と「コーヒー豆（産地別）」
(straight/pg102.html、12銘柄、単一商品が2箇所からリンクされているため
URLで重複排除)の2カテゴリのみをコーヒー豆として対象とする。「ドリップ
バッグ」「アイスコーヒー」「コーヒーギフト」「その他」は別カテゴリであり
最初から巡回対象に含めない(カテゴリ選定による除外)。各カテゴリ一覧
ページはページネーションなし(全銘柄が1ページに収まる)。

各銘柄の商品詳細ページ(pgNNN.html)には、重量違いごとに1つの
`<span class="bind_cart" data-product="<id>">`が埋め込まれており(例:
ヒグラシブレンド「ソフト」は200g/500g/1kgの3IDを持つ)、これがBiND Cart
商品IDである。IDごとにAPIを呼び出し、価格(price)・重量ラベル(sale_text、
例:"200g"「1kg"）・表示フラグ(display_flg、"0"=非表示/完売時に多い、
"1"=表示中)を取得する。

【非コーヒー豆商品の除外について】
実データ確認済み: 「コーヒー豆（ブレンド）」「コーヒー豆（産地別）」の
2カテゴリに限定して巡回しているため、ドリップバッグ・リキッドアイス
コーヒー・ギフトセット等は取得対象に含まれない。カテゴリ内の21銘柄は
いずれも単一銘柄のコーヒー豆(生豆ブレンド or 単一産地)であり、詰め合わせ
セット等の除外対象商品は確認されなかった。念のためNON_BEAN_KEYWORDS
("セット", "詰め合わせ", "ギフト")を用意しておく。

【重量違いの重複について】
実データ確認済み: 同一銘柄でも「200g」「500g入り袋」「1kg」のように
複数の重量が別々のBiND Cart商品ID(=別商品名の場合とページ内で名前が
同一の場合が混在)として登録されている。重量情報はタイトル文字列ではなく
API側の構造化フィールド(sale_text)から取得するのが確実なため(例:
「ヒグラシブレンド ソフト」という商品名が200g版・1kg版の両方で全く同一
表記であり、タイトルからの重量パースでは区別できないことを実データで
確認済み)、1つの商品詳細ページ内で複数の商品IDを重量(sale_text)の昇順で
比較し、最小重量の商品IDを代表として採用する。
"""

import re

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_stock_status

SHOP_INFO = {
    "name": "ヒグラシ珈琲",
    "url": "https://higurashi-coffee.com/",
    "platform": "BiND Cart",
    "address": "兵庫県豊岡市千代田町1-5",
    "prefecture": "兵庫県",
    "robots_txt_status": "実質許可(2026-09確認。higurashi-coffee.com・"
                          "shops-api2.bindcart.comともにrobots.txt自体が"
                          "存在せず(404)、クロール制限の記述がないため実質無制限と判断)",
}

BASE_URL = "https://higurashi-coffee.com"
CATEGORY_PATHS = [
    "/onlineshop/blendcoffee/pg97.html",   # コーヒー豆(ブレンド)
    "/onlineshop/straight/pg102.html",     # コーヒー豆(産地別)
]
BINDCART_API_URL = "https://shops-api2.bindcart.com/pagep.php"
BINDCART_SHOP_JSON_URL = "http://higurashi.shops.bindcart.com/JSON/pagep.php"

REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = ["セット", "詰め合わせ", "ギフト"]
WEIGHT_PATTERN = re.compile(r"(\d+)\s*(kg|ｋｇ|g|ｇ)", re.IGNORECASE)
PRODUCT_ID_PATTERN = re.compile(r'data-product="(\d+)"')


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp


def fetch_product_page_list() -> list[dict]:
    """カテゴリ一覧ページから、商品詳細ページURLの一覧を取得する(重複排除)。"""
    pages: dict[str, str] = {}
    for path in CATEGORY_PATHS:
        resp = fetch(f"{BASE_URL}{path}")
        soup = BeautifulSoup(resp.text, "html.parser")
        for col in soup.select("div.column"):
            h4 = col.find("h4")
            a = col.find("a", attrs={"data-pid": True})
            if not h4 or not a:
                continue
            href = a.get("href") or ""
            m = re.search(r"(/onlineshop/\w+/pg\d+\.html)", href)
            if not m:
                continue
            product_url = BASE_URL + m.group(1)
            if product_url not in pages:
                pages[product_url] = h4.get_text(strip=True)
    return [{"url": url, "title": title} for url, title in pages.items()]


def fetch_variant_ids(product_url: str) -> list[str]:
    resp = fetch(product_url)
    ids = sorted(set(PRODUCT_ID_PATTERN.findall(resp.text)))
    return [pid for pid in ids if pid]


def fetch_variant_detail(product_id: str) -> dict | None:
    args = f'a:1:{{i:0;s:{len(product_id)}:"{product_id}";}}'
    params = {
        "callback": "jQuery0",
        "url": BINDCART_SHOP_JSON_URL,
        "system": "Shopping",
        "class": "Searches",
        "method": "ProductDetail",
        "args": args,
    }
    resp = requests.get(BINDCART_API_URL, params=params, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    m = re.search(r"^jQuery0\((.*)\);?\s*$", resp.text.strip(), re.DOTALL)
    if not m:
        return None
    import json
    data = json.loads(m.group(1))

    weight_g = None
    wm = WEIGHT_PATTERN.search(data.get("sale_text") or "")
    if wm:
        value = int(wm.group(1))
        unit = wm.group(2).lower()
        weight_g = value * 1000 if unit in ("kg", "ｋｇ") else value

    return {
        "product_id": data.get("product_id"),
        "title": (data.get("product_name") or "").strip(),
        "price": int(data["price"]) if data.get("price") not in (None, "") else None,
        "weight_g": weight_g,
        "display_flg": data.get("display_flg"),
    }


def pick_canonical_variant(variants: list[dict]) -> dict | None:
    valid = [v for v in variants if v and v.get("title")]
    if not valid:
        return None
    return min(valid, key=lambda v: v["weight_g"] if v["weight_g"] is not None else float("inf"))


def build_record(variant: dict) -> dict | None:
    title = variant["title"]
    if not title or any(kw in title for kw in NON_BEAN_KEYWORDS):
        return None

    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": variant["price"],
            "product_url": SHOP_INFO["url"],
        }

    structural_out_of_stock = variant.get("display_flg") == "0"
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
        "price": variant["price"],
        "weight_g": variant["weight_g"],
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": None,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    product_pages = fetch_product_page_list()

    records = []
    flavored_records = []
    for page in product_pages:
        try:
            variant_ids = fetch_variant_ids(page["url"])
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {page['url']} ({e})")
            continue

        variants = []
        for pid in variant_ids:
            try:
                detail = fetch_variant_detail(pid)
            except (requests.RequestException, ValueError) as e:
                print(f"[warn] BiND Cart API取得失敗: product_id={pid} ({e})")
                continue
            if detail:
                variants.append(detail)

        canonical = pick_canonical_variant(variants)
        if canonical is None:
            continue
        canonical["product_url"] = page["url"]

        detail = build_record(canonical)
        if detail is None:
            continue
        if detail.get("is_flavored"):
            detail["product_url"] = page["url"]
            flavored_records.append(detail)
        else:
            detail["product_url"] = page["url"]
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
    with open("data_higurashicoffee.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_higurashicoffee.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
