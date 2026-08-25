# -*- coding: utf-8 -*-
"""
scrape_coulane.py

クラーヌ(Coulane、coulane.jp、神奈川県相模原市)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)製で、PHILOCOFFEAと同一プラットフォーム。

robots.txt確認済み(2026-08時点): PHILOCOFFEAと同一の記述(User-agent: * は /secure/
と /cart/ のみDisallow。AhrefsBot等SEO分析系ボットは個別に全面禁止だが対象外)。

【カテゴリ構成について】実データ確認済み(2026-08時点):
サイト上部メニューには「酸味/苦味/バランスのあるコーヒー」という味わい軸の3分類
(gid=2520658/2520659/2520660)が目立つ位置にあるが、これは全商品を横断的に
タグ付けしたビューにすぎない。実際の商品カテゴリ階層(パンくずリストのcbid)は
以下の6つで、うち豆売り(グラム単位でグラインド方法を選んで購入する形式)は
最初の4つのみ:
  - cbid=2692103 ストレートコーヒー
  - cbid=2692104 ブレンドコーヒー
  - cbid=2692105 カフェインレスコーヒー
  - cbid=2699406 アイスコーヒー(アイス用ブレンド。ドリップバッグ等と違い実際に
    豆のまま/挽き方選択の商品ページを持つことを実データで確認済み)
  - cbid=2694677 ドリップバッグ(対象外。挽き方バリアントを持たない固定パック商品)
  - cbid=2699407 水出しアイスコーヒーパック(対象外。同上)
4カテゴリの商品は重複が無いことを確認済み(pidの和集合がそのまま合計件数と一致)。

【商品ページの構造について】
商品詳細ページに `var Colorme = {...};` という埋め込みJSONがあり(PHILOCOFFEAと
同じ仕組み)、税込価格(product.sales_price_including_tax)をここから取得する。
一方でPHILOCOFFEAの「BEANS DATA」のような構造化表は無く、産地・農園・品種等の
情報はすべて自由記述の説明文(div.p-product-body__description)に書かれている。
ただし末尾に必ず `[焙煎]中煎り` `[内容量]200g` のような角カッコ付きラベルの行が
あり、焙煎度(3段階の粗い表現なのでroast_hintとして保持)と内容量はここから
確実に取れる。産地国・グレード・農園名・品種は商品名(例:「ニカラグア SHG
キータスウエノス農園」)から取得する方が確実(自由記述の説明文は長い読み物調で
構造化キー抽出に向かない)。flavor_notesはJSON-LD(application/ld+json、
"@type":"Product")のdescriptionフィールドから取る(自由記述より短く、
一貫してテイスティングノートの体裁になっていることを実データで確認済み)。

在庫管理はしていない店舗(Colorme JSONの"inventory_control":"none"を確認済み、
実際に品切れ表示のある商品も site全体で見つからなかった)ため、構造化な在庫
フラグは使わず商品名のテキストのみで在庫状態を判定する。
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
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "Coulane",
    "url": "https://www.coulane.jp/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "神奈川県相模原市中央区横山3-17-4",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。PHILOCOFFEAと同一の記述。/secure/と/cart/以外は制限なし)",
}

BASE_URL = "https://www.coulane.jp/"
CRAWL_DELAY_SECONDS = 1  # robots.txt確認済み(2026-08時点): Crawl-delay指定なし
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 豆売り(グラム単位でグラインド方法を選ぶ形式)の4カテゴリのみ対象。
# ドリップバッグ(2694677)・水出しアイスコーヒーパックス(2699407)は対象外
# (実データ確認済み: 挽き方バリアントを持たない固定パック商品)。
BEAN_CATEGORY_IDS = [2692103, 2692104, 2692105, 2699406]

COLORME_JSON_START_PATTERN = re.compile(r"var\s+Colorme\s*=\s*\{")
JSONLD_DESCRIPTION_PATTERN = re.compile(r'"description":"([^"]*)"')


def extract_colorme_json(html_text: str) -> dict | None:
    """`var Colorme = {...};` を波括弧の対応を数えて厳密に取り出す。
    実データ確認済み: このページには `var Colorme = ` より後にも(別の
    インラインスクリプトの)"};" が複数回登場するため、素朴な貪欲マッチの
    正規表現(`\{.*\};`)では対象を大きく超えて誤った範囲を拾ってしまい、
    json.loadsが失敗して常にNoneが返る不具合になっていた。文字列リテラル内の
    括弧・エスケープ済み引用符を無視しながら開き括弧の数を数え、対応する
    閉じ括弧の位置で正確に切り出す。"""
    m = COLORME_JSON_START_PATTERN.search(html_text)
    if not m:
        return None
    start = m.end() - 1  # 開き括弧 "{" の位置
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(html_text)):
        ch = html_text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html_text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

# 説明文末尾の角カッコラベル行(例: [焙煎]中煎り、[内容量]200g)。
BRACKET_ROAST_PATTERN = re.compile(r"\[焙煎\]\s*([^\s<]+)")
BRACKET_WEIGHT_PATTERN = re.compile(r"\[内容量\]\s*(\d+)\s*[gｇ]")

# 農園・組合名は商品名の末尾付近に「〇〇農園」「〇〇組合」という形で現れることが
# 実データで確認できた(例:「キータスウエノス農園」「インカワシ組合」)。
FARM_NAME_PATTERN = re.compile(r"([^\s　]{2,20}(?:農園|組合))")


def fetch_page(url: str) -> tuple[BeautifulSoup, str]:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    # このサイトはEUC-JP。requestsの自動エンコーディング推定が外れることがあるため、
    # 常にEUC-JPとして明示デコードする(PHILOCOFFEA・MUIはUTF-8のため意識しなかった
    # 差異。実データ確認済み: meta charsetがeuc-jp)。
    resp.encoding = "euc-jp"
    html_text = resp.text
    soup = BeautifulSoup(html_text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup, html_text


def extract_price(html_text: str) -> int | None:
    data = extract_colorme_json(html_text)
    if not data:
        return None
    return data.get("product", {}).get("sales_price_including_tax")


def extract_flavor_notes(html_text: str) -> str | None:
    m = JSONLD_DESCRIPTION_PATTERN.search(html_text)
    return m.group(1) if m and m.group(1) else None


def parse_product_detail(url: str) -> dict:
    soup, html_text = fetch_page(url)

    name_el = soup.select_one("h1.p-product-body__name, h2.spProductName")
    raw_name = name_el.get_text(strip=True) if name_el else ""
    if not raw_name:
        # テーマ差異への保険。JSON側のproduct.nameを最終手段として使う
        data = extract_colorme_json(html_text)
        if data:
            raw_name = data.get("product", {}).get("name", "")

    price = extract_price(html_text)
    stock_status = detect_stock_status(raw_name)

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

    desc_el = soup.select_one("div.p-product-body__description")
    desc_text = desc_el.get_text("\n") if desc_el else ""

    roast_match = BRACKET_ROAST_PATTERN.search(desc_text)
    roast_hint = roast_match.group(1) if roast_match else None

    weight_match = BRACKET_WEIGHT_PATTERN.search(desc_text)
    weight_g = int(weight_match.group(1)) if weight_match else None

    farm_match = FARM_NAME_PATTERN.search(raw_name)
    farm_name = farm_match.group(1) if farm_match else None

    variety = None
    for kw, normalized in VARIETY_KEYWORDS.items():
        if kw in raw_name:
            variety = normalized
            break

    parsed = apply_category_hint_fallback(parsed, None)
    flavor_notes = extract_flavor_notes(html_text)

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
        "roast_hint": roast_hint,
        "roast_selectable": True,  # 実データ確認済み: 全商品が挽き方バリアント(豆のまま含む)を持つ
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_name": farm_name,
        "variety": variety,
        "flavor_notes": flavor_notes,
        "weight_g": weight_g,
        "price": price,
        "stock_status": stock_status,
        "product_url": url,
    }


# --- 一覧ページのクロール処理 -------------------------------------------------
# 実データ確認済み(2026-08時点): 商品ブロックはli.c-product-list__item、
# ページ送りは ?mode=cate&cbid=<ID>&csid=0&sort=n&page=<N> というGETアクセス
# 可能なURLパターンで、末尾を超えたページ(0件)を検出したら終端とみなす。


def scrape_category_list_page(cbid: int, page: int) -> list[dict]:
    url = f"{BASE_URL}?mode=cate&cbid={cbid}&csid=0&sort=n"
    if page > 1:
        url += f"&page={page}"
    soup, _ = fetch_page(url)
    items = soup.select("li.c-product-list__item")

    results = []
    for item in items:
        name_el = item.select_one("a.c-product-list__name")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href

        price = None
        price_el = item.select_one("div.c-product-list__price")
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
            "out_of_stock": stock_status != "販売中",
        })
    return results


def scrape_all_products(fetch_details: bool = True, max_pages_per_category: int = 20) -> tuple[list[dict], list[dict]]:
    """4カテゴリ(ストレート/ブレンド/カフェインレス/アイスコーヒー)を全ページ辿り、
    各商品の詳細ページもパースして結合する。カテゴリ間で商品の重複が無いことを
    実データで確認済みのため、URL単位の重複排除は保険としてのみ行う。

    戻り値は (products, flavored_products) のタプル。
    """
    all_list_items: dict[str, dict] = {}
    for cbid in BEAN_CATEGORY_IDS:
        for page in range(1, max_pages_per_category + 1):
            items = scrape_category_list_page(cbid, page)
            if not items:
                break
            for item in items:
                all_list_items[item["product_url"]] = item
            time.sleep(CRAWL_DELAY_SECONDS)

    if not fetch_details:
        return list(all_list_items.values()), []

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in all_list_items.values():
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
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            if prev:
                records.append(prev)

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
        with open("data_coulane.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_coulane.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
