# -*- coding: utf-8 -*-
"""
scrape_kitami.py

きたみcoffee(kitamicoffee.com、千葉県八千代市)の商品情報を取得する。
レガシーEC-CUBE(2.x系、/shop/products/detail.php?product_id=N という
クエリ文字列URL方式。Daphneの/products/detail/というパス方式のEC-CUBE
4.xとは異なるバージョン)。このプロジェクト初のEC-CUBEレガシー版対応。

robots.txt確認済み(2026-09時点): ルート・/shop/配下ともrobots.txt自体が
存在せず404(ロリポップの汎用404ページが返るのみ)。実質全面許可。

【カテゴリ構造について】
実データ確認済み: カテゴリが「器具」「器具(コーヒーミル)」「セット商品」
「ギフト商品」「コーヒーバッグ」「アイスコーヒー」「その他」等の非豆
カテゴリと、「ストレートコーヒー」「ブレンドコーヒー」「軽め/中間/深めの
コーヒー」「カフェインレスコーヒー」「この季節に合うコーヒー」「悩んだ時の
オススメ」「際立つ味わいのコーヒー」等の豆カテゴリが混在し、かつ豆
カテゴリ同士も同じ商品が複数カテゴリに重複登録される「ビュー」的な
構造になっている(Daphneの「新入荷」と同様、ただし複数カテゴリが互いに
部分的にしか重ならない点がDaphneより複雑)。そのため対象カテゴリを
ストレート(7)・ブレンド(18)・軽め(19)・中間(20)・深め(21)・季節(26)・
オススメ(28)・カフェインレス(41)・際立つ味わい(46)の9カテゴリの和集合
(product_id単位で自然に重複排除)とし、その中からNON_BEAN_KEYWORDSで
ドリップバッグ・ギフトセット・水出しアイスパック・瓶入り濃縮コーヒー等を
除外する(実データ確認済み: 43件の重複込み一覧から23件の豆単品に絞り込み)。
「アイスコーヒー」カテゴリ(47)自体は対象に含めていないが、そこに属する
「アイスコーヒーブレンド」等の重量表記(200g/500g)を持つ実豆商品は
ブレンド(18)カテゴリ経由で既に対象に含まれることを確認済み。

【重量バリエーションについて】
実データ確認済み: 商品詳細ページのJS変数`eccube.classCategories`に
「豆・粉」(classcategory_id1、豆のまま/粉に挽く/エスプレッソ用極細挽きの
3種、商品によらず値は共通で「豆のまま」=11)×「重量」(classcategory_id2、
200g/500gが多いが一部15g固定の単一サイズ商品もある)の価格・在庫が
構造化JSONとして入っている(Daphneと同じ`eccube.classCategories`だが、
id1/id2の役割が逆でDaphneはid1=重量・id2=豆orタイプ、きたみcoffeeは
id1=豆・粉タイプ・id2=重量という違いがある)。「豆のまま」の中から
最小重量を代表バリアントとして採用する。単一サイズ商品(重量名が空文字)は
重量情報をタイトル中の表記(例:「15g」)から補完する。価格(price02)は
一覧ページの表示(税込)と一致することを実データ確認済み。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "きたみcoffee",
    "url": "https://kitamicoffee.com/",
    "platform": "EC-CUBE",
    "address": "千葉県八千代市",
    "prefecture": "千葉県",
    "robots_txt_status": "実質許可(2026-09確認。robots.txt自体が存在せず404、"
                          "ロリポップの汎用404ページが返るのみ)",
}

BASE_URL = "https://kitamicoffee.com/shop"
# 理由はモジュールdocstring参照
LIST_CATEGORIES = {
    "7": "ストレートコーヒー",
    "18": "ブレンドコーヒー",
    "19": "軽めのコーヒー",
    "20": "中間のコーヒー",
    "21": "深めのコーヒー",
    "26": "この季節に合うコーヒー",
    "28": "悩んだ時のオススメ",
    "41": "カフェインレスコーヒー",
    "46": "際立つ味わいのコーヒー",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

NON_BEAN_KEYWORDS = [
    "セット", "ギフト", "コーヒーバッグ", "水出し", "アイスパック", "ロマネ", "カスカラ", "杯分",
]
CLASS_CATEGORIES_PATTERN = re.compile(r"eccube\.classCategories\s*=\s*(\{.*?\});", re.DOTALL)
CLASSCAT1_OPTION_PATTERN = re.compile(r'<option label="([^"]*)" value="(\d+)">')
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def pick_canonical_variant(html: str, title: str) -> tuple[int | None, int | None, bool]:
    """理由はモジュールdocstring参照。「豆のまま」の中から最小重量を採用する。
    戻り値は(weight_g, price, in_stock)。"""
    m = CLASS_CATEGORIES_PATTERN.search(html)
    if not m:
        return None, None, True
    try:
        class_categories = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, None, True

    bean_id1 = None
    for label, value in CLASSCAT1_OPTION_PATTERN.findall(html):
        if label == "豆のまま":
            bean_id1 = value
            break

    group = class_categories.get(bean_id1) if bean_id1 else None
    if not group:
        return None, None, True

    candidates = []
    for key, entry in group.items():
        if key == "#" or not isinstance(entry, dict):
            continue
        price_raw = entry.get("price02")
        if not price_raw:
            continue
        price = int(str(price_raw).replace(",", ""))
        weight_match = WEIGHT_PATTERN.search(entry.get("name") or "")
        weight_g = int(weight_match.group(1)) if weight_match else None
        in_stock = bool(entry.get("stock_find"))
        candidates.append((weight_g, price, in_stock))

    if not candidates:
        return None, None, True

    title_weight_match = WEIGHT_PATTERN.search(title)
    title_weight = int(title_weight_match.group(1)) if title_weight_match else None

    with_weight = [c for c in candidates if c[0] is not None]
    if with_weight:
        weight_g, price, in_stock = min(with_weight, key=lambda c: c[0])
        return weight_g, price, in_stock

    # 単一サイズ商品(重量名が空文字)はタイトル中の重量表記で補完する
    weight_g, price, in_stock = candidates[0]
    return (title_weight or weight_g), price, in_stock


def build_record(product_url: str, title: str, html: str, category_hint: str) -> dict:
    parsed = parse_product(title)
    weight_g, price, in_stock = pick_canonical_variant(html, title)

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

    parsed = apply_category_hint_fallback(parsed, category_hint)
    stock_status = detect_stock_status(title, not in_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "price": price,
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("title")
    raw_title = title_el.get_text(strip=True) if title_el else ""
    title = raw_title.rsplit(" / ", 1)[-1].strip() if " / " in raw_title else raw_title
    if not title:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    if any(kw in title for kw in NON_BEAN_KEYWORDS):
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "non_bean": True,
            "product_url": url,
        }

    return build_record(url, title, html, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/products/list.php?category_id={cid}")
    results = []
    for link_el in soup.select('a[href*="products/detail.php?product_id="]'):
        href = link_el.get("href", "")
        img_el = link_el.select_one("img[alt]")
        title = img_el.get("alt", "").strip() if img_el else ""
        if not title:
            continue
        product_url = href if href.startswith("http") else f"https://kitamicoffee.com{href}"
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
            if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
                continue
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            elif not detail.get("non_bean"):
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

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
        with open("data_kitami.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_kitami.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
