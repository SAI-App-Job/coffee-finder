# -*- coding: utf-8 -*-
"""
scrape_denimbis.py

Denim bis(おちゃのこネット/Ocnkプラットフォーム)の商品一覧をスクレイピングし、
coffee_parser.pyでパースした上でJSON(SHOP+PRODUCT相当)として出力する。

セレクタは実際のHTML(商品一覧ページ・商品詳細ページ)を確認した上で作成済み(2026-08時点)。
ただしサイト側のテンプレートが将来変更された場合は再調整が必要。

robots.txt確認済み(2026年8月時点): 主要AIクローラー(GPTBot等)は明示的に許可、
一般クローラーへの制限記述なし。courtesy delayとしてクロール間隔を設定。

【差分ベーススクレイピング】一覧ページ(軽量)の時点で商品名・価格帯・
カテゴリが前回(data/products.json)と変わっていない商品は、詳細ページの
再取得をスキップして前回のレコードをそのまま使い回す(previous_data.py参照)。
"""

import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, extract_from_description
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Denim bis",
    "url": "https://www.denimbis.com/",
    "platform": "おちゃのこネット(Ocnk)",
    "address": "神奈川県川崎市",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。一般クローラーへの制限なし)",
}

# カテゴリID → category_hint(カテゴリ名)。トップページ(全商品ページ)のナビゲーションから
# 実データ確認済み(2026-08時点)。
CATEGORY_MAP = {
    1: "アフリカ諸国",
    2: "オリジナルブレンド",
    3: "中米諸国",
    4: "南米諸国",
    5: "太平洋／大西洋諸国",
    6: "アジア／オセアニア諸国",
    7: "カフェインレス",
    8: "コーヒードリップパック",
    10: "おやつ",
    11: "オリジナルグッズ",
    13: "今月のスタッフおすすめ3種SET",
}

# コーヒー豆(生豆・焙煎豆)以外のカテゴリは商品対象から除外
# ドリップパックは形態が異なる(挽いた豆をパック化した別商品ライン)ため一旦除外。
# 将来的に別商品タイプとして扱いたい場合は個別に対応する。
EXCLUDED_CATEGORIES = {"おやつ", "オリジナルグッズ", "コーヒードリップパック"}

BASE_URL = "https://www.denimbis.com"
CRAWL_DELAY_SECONDS = 3  # robots.txtのdotbot/AhrefsBot向け指定に倣ったcourtesy設定
REQUEST_HEADERS = {
    # 収集主体が分かるよう、一般的なブラウザUAではなく素性を示すUAを推奨
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_category(category_id: int, category_name: str) -> list[dict]:
    """1カテゴリ分の商品一覧をページネーション込みで取得する。

    実データ確認済みの構造(2026-08時点):
    - 商品一覧本体は `div.page_box.itemlist` の中の `li.list_item_cell` >
      `div.item_data[data-product-id]`
    - 商品名は `p.item_name span.goods_name`
    - 商品リンクは `a.item_data_link`(絶対URL)
    - 価格は `span.figure` に「890円～4,010円」のような範囲表記
    - 次ページの有無は `a.to_next_page` の存在で判定

    【重要】`li.list_item_cell` はカテゴリ本体の商品一覧だけでなく、全カテゴリ
    ページ共通のサイドバー「おすすめ商品」ウィジェット(`div.side_box.item_box.recommend`)
    内の商品にも同じクラスが使われている。ページ全体を対象にセレクタを掛けると、
    このおすすめ商品(常に同じ2〜3商品)が全カテゴリで重複して取得されてしまう
    不具合が実データで確認された(45件中24件が重複という形で顕在化)。
    そのため、カテゴリ本体のコンテナ(`div.page_box.itemlist`)に範囲を絞って
    から商品セルを探す。
    """
    products = []
    page = 1

    while True:
        url = f"{BASE_URL}/product-list/{category_id}"
        if page > 1:
            url += f"?page={page}"

        soup = fetch_page(url)
        container = soup.select_one("div.page_box.itemlist")
        items = container.select("li.list_item_cell") if container else []
        if not items:
            break

        for item in items:
            data_el = item.select_one("div.item_data")
            name_el = item.select_one("p.item_name span.goods_name")
            link_el = item.select_one("a.item_data_link")
            price_el = item.select_one(".price .selling_price .figure")

            if not name_el or not data_el:
                continue

            raw_name = name_el.get_text(strip=True)
            product_id = data_el.get("data-product-id")
            product_url = link_el["href"] if link_el else (f"{BASE_URL}/product/{product_id}" if product_id else None)

            price_min, price_max = None, None
            if price_el:
                price_text = price_el.get_text(strip=True)  # 例: "890円～4,010円"
                price_numbers = re.findall(r"[\d,]+(?=円)", price_text)
                if price_numbers:
                    price_min = int(price_numbers[0].replace(",", ""))
                    price_max = int(price_numbers[-1].replace(",", ""))

            products.append({
                "product_id": product_id,
                "raw_name": raw_name,
                "price_min": price_min,
                "price_max": price_max,
                "product_url": product_url,
                "category_hint": category_name,
            })

        # 次ページの有無を「次へ」リンクの存在で判定
        next_link = soup.select_one("a.to_next_page")
        if not next_link:
            break
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    return products


def fetch_product_description(product_url: str) -> str:
    """商品詳細ページの説明文を取得する(精選方法・栽培品種の補強用)。

    <p>タグ区切りを改行(separator="\\n")で連結する。空文字区切りにすると
    「栽培品種：ムンドノーボ、カツカイ、カツアイ」の直後に「精製処理：ナチュラル」が
    そのまま連結され、品種抽出の正規表現が精選方法の文字列まで巻き込んでしまう
    不具合が実データ検証で判明したため。
    """
    soup = fetch_page(product_url)
    desc_el = soup.select_one("div.item_desc_text")
    return desc_el.get_text(separator="\n", strip=True) if desc_el else ""


def build_product_records(
    raw_items: list[dict], previous: dict, fetch_details: bool = True
) -> tuple[list[dict], list[dict]]:
    """スクレイピングした生データをパースし、PRODUCTテーブル相当のレコードに変換する。

    fetch_details=True の場合、商品名だけで精選方法が特定できなかった商品について
    詳細ページの説明文(「精製処理：○○」形式)も確認する。リクエスト数が増えるため
    crawl delay を挟む。

    previous(product_url→前回レコード)に一致する商品があり、かつ一覧ページで
    分かる情報(商品名・価格帯・カテゴリ)が前回と変わっていない場合は、詳細ページの
    取得自体をスキップして前回のレコードをそのまま使い回す(差分ベーススクレイピング)。

    戻り値は (products, flavored_products) のタプル。フレーバーコーヒーは
    産地・精選方法の個性を扱う本アプリの趣旨と異なる商品カテゴリのため、
    完全に分離して返す(本体のproductsには一切含めない)。
    """
    now = datetime.now(timezone.utc).isoformat()
    records = []
    flavored_records = []

    for item in raw_items:
        if item.get("category_hint") in EXCLUDED_CATEGORIES:
            continue

        prev = previous.get(item.get("product_url"))
        if is_unchanged(
            prev,
            raw_name=item["raw_name"],
            price_min=item.get("price_min"),
            price_max=item.get("price_max"),
            category_hint=item.get("category_hint"),
        ):
            records.append(prev)
            continue

        parsed = parse_product(item["raw_name"])

        # フレーバーコーヒーは産地判定・詳細ページ取得をスキップし、別リストに分離
        if parsed["is_flavored"]:
            flavored_records.append({
                "shop_name": SHOP_INFO["name"],
                "product_id": item.get("product_id"),
                "raw_name": item["raw_name"],
                "flavor_name": parsed["flavor_name"],
                "price_min": item.get("price_min"),
                "price_max": item.get("price_max"),
                "product_url": item.get("product_url"),
                "scraped_at": now,
            })
            continue

        parsed = apply_category_hint_fallback(parsed, item.get("category_hint"))

        variety_note = None
        if fetch_details and not parsed["processing_method"] and item.get("product_url"):
            try:
                description = fetch_product_description(item["product_url"])
                extra = extract_from_description(description)
                if extra["processing_method"]:
                    parsed["processing_method"] = extra["processing_method"]
                variety_note = extra["variety_note"]
                time.sleep(CRAWL_DELAY_SECONDS)
            except requests.RequestException as e:
                print(f"[warn] 詳細ページ取得失敗: {item.get('product_url')} ({e})")

        records.append({
            "shop_name": SHOP_INFO["name"],
            "product_id": item.get("product_id"),
            "raw_name": item["raw_name"],
            "category": parsed["category"],
            "category_hint": item.get("category_hint"),
            "origin_country": parsed["origin_country"],
            "origin_source": parsed["origin_source"],
            "designated_brand": parsed["designated_brand"],
            "processing_method": parsed["processing_method"],
            "variety_note": variety_note,
            "grade": parsed["grade"],
            "roast_level": parsed["roast_level"],  # Denim bisは注文時選択のため基本null
            "roast_selectable": parsed["roast_level"] is None and parsed["category"] == "ストレート",
            "post_processing_tags": parsed["post_processing_tags"],
            "price_min": item.get("price_min"),
            "price_max": item.get("price_max"),
            "product_url": item.get("product_url"),
            "scraped_at": now,
        })

    return records, flavored_records


def dedupe_raw_items(raw_items: list[dict]) -> list[dict]:
    """product_url(無ければproduct_id)をキーに1商品1件へ統合する安全策。

    scrape_categoryのセレクタ修正でサイドバー「おすすめ商品」由来の重複は
    解消したが、商品が実際に複数の実カテゴリ(例: 南米諸国 かつ カフェインレス)
    に属していて正規のカテゴリ一覧同士で重複するケースは今後もありうるため、
    保険として残す。除外カテゴリ由来のエントリより通常カテゴリ由来のエントリを
    優先する(除外カテゴリに先に出現しただけで、実際は通常カテゴリにも属する
    商品が丸ごと除外されてしまわないように)。
    """
    best_by_key: dict[str, dict] = {}
    for item in raw_items:
        key = item.get("product_url") or item.get("product_id")
        if not key:
            continue
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = item
            continue
        if existing.get("category_hint") in EXCLUDED_CATEGORIES and item.get("category_hint") not in EXCLUDED_CATEGORIES:
            best_by_key[key] = item
    return list(best_by_key.values())


def main():
    all_raw_items = []
    for category_id, category_name in CATEGORY_MAP.items():
        print(f"[scrape] category={category_name} (id={category_id})")
        items = scrape_category(category_id, category_name)
        all_raw_items.extend(items)
        time.sleep(CRAWL_DELAY_SECONDS)

    before_dedupe = len(all_raw_items)
    all_raw_items = dedupe_raw_items(all_raw_items)
    if before_dedupe != len(all_raw_items):
        print(f"[info] 重複除去: {before_dedupe}件 → {len(all_raw_items)}件(product_url基準)")

    previous = load_previous_products(SHOP_INFO["name"])
    records, flavored_records = build_product_records(all_raw_items, previous)

    output = {
        "shop": SHOP_INFO,
        "products": records,
        # フレーバーコーヒーは産地・精選方法の個性を扱う本アプリの趣旨と異なるため
        # 完全に分離。フロントエンドの通常商品一覧には表示しない
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_denimbis.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_denimbis.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
