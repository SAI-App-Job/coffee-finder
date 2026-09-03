# -*- coding: utf-8 -*-
"""
scrape_tamaji.py

たまじ珈琲(tamajicoffee.com、東京都杉並区成田東)の商品情報を取得する。
WordPress + USC-e-Shop(Useful Simple Cart)というこのプロジェクト初対応の
プラットフォーム。「注文後焙煎」(受注焙煎)が売りの実店舗(Google Maps実在
確認済み、★4.7)。

robots.txt確認済み(2026-09時点): User-agent: *に対し/wp-admin/のみDisallow
(admin-ajax.phpは例外的にAllow)。それ以外は制限なし。

【商品カタログの取得元について】
実データ確認済み(2026-09時点): /category/<タグ名>/(例: /category/nigami_koku/、
サイトのナビゲーションに現れる「苦みとコク」等の味わい別カテゴリページ)は
アクセスできるが商品が1件も表示されない(空のページ)。一方、/online_shop/
ページ自体に全商品がarticle > section(h4見出し=カテゴリ名) > div.item_blocks
という構造で直接埋め込まれており、実際のカタログはこちらが一次情報である
ことを確認した。そのため本スクレイパーは/online_shop/を1回だけ取得し、
対象セクション内の商品コード・商品名・価格・URLをその場で抽出する
(カテゴリページを個別にクロールしない)。

【対象セクションについて】
実データ確認済み: /online_shop/には15のh4セクションがあり、コーヒー豆の
専用商品(9セクション、計47件)と、豆単体ではない商品(6セクション)が
混在している。
  対象(コーヒー豆): 軽くてソフト(5)・軽い中にも苦みと酸味(5)・
    酸味と苦みの良いバランス(9)・苦みとコク(11)・苦みとキレ(4)・
    カフェオレ専用(2)・エスプレッソ専用(1)・カフェインレス(5)・
    裏メニュー(5、実データ確認済み: スタッフ考案のブレンドで実際に
    コーヒー豆の商品であることを確認済み)
  対象外: 珈琲の好みが決まっていないお客さま(2、100g×2種のお試しパック)・
    ギフト(11)・『tamajiドリップ』(13、ドリップバッグ)・
    水出しアイス専用(8、液体/専用形態の水出しコーヒー)・
    有料袋(4、豆ではなく紙袋・巾着袋そのもの)
  ※「◆ たまじチケット」記事全体(サブスクリプション)も対象外。

【商品詳細ページの構造(div.item_content、h5見出し+p値の繰り返し)について】
実データ確認済み: <h5>原産国</h5>に続く<p>が1つならストレート(単一産地)、
複数連続するならブレンド(複数産地の配合)と判定できる。商品名に「ブレンド」
という語を含まないブレンド商品(例:「GOEMONブラック」が実際はメキシコ/
インドネシア/ブラジルの3産地配合)が存在することを確認済みのため、商品名
ではなくこの構造(原産国の<p>の個数)でブレンド判定を行う(is_blend参照)。
ただし複数産地が必ず別々の<p>に分かれるとは限らず、「たまじブレンドJOKER」
は<p>が1個だけで中身が「ジャマイカ、ブラジル」とカンマ区切りでまとめられて
いた(実データ検証で判明。当初<p>の個数だけで判定していたところ、この商品が
category="ブレンド"なのにorigin_country="ブラジル"というproduction矛盾を
起こしたため修正)。そのため各<p>の値をさらにカンマで分割してから件数を
数える。なお「たまじ春ブレンド」のように原産国欄自体が存在しない(0件)商品も
あり、その場合のみ商品名解析の「ブレンド」判定にフォールバックする。
<h5>おすすめロースト</h5>の値は「3／中深焙煎（酸味と苦み）」のような
1〜9段階の独自表記で、プロ向け8段階表記と粒度が異なるためroast_hintとして
保持する(受注焙煎方式のためroast_selectable=True)。

【重量について】
実データ確認済み: 価格表(table.sku_price_pack)の数量表示は「105g」だが、
これは焙煎前の生豆重量で、注文オプション(itemOption)には「100g（豆・挽き）」
という顧客向けの表示重量が別に存在する(説明文に「価格は生豆105gの価格です。
焙煎すると水分が15～20%ほど飛びますので、その分目減りします」という注記が
あり、焙煎後の正確な重量は幅を持つ概算のみでピンポイントの値が無い)。
HIMONYA FIVE COFFEEのように焙煎後の正確な重量が明記されていないため、
不確かな計算値を作らず、顧客が実際に選択する表示単位である「100g」を
weight_gとして採用する。

【在庫状態について】
実データ確認済み: 商品詳細ページのdiv.item_stockに「在庫状態 : 在庫有り」
という構造化されたテキストがある。「在庫有り」以外(在庫なし/品切れ等)を
一時的な品切れとして扱う。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, normalize_processing_method, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "たまじ珈琲",
    "url": "https://tamajicoffee.com/",
    "platform": "WordPress + USC-e-Shop",
    "address": "東京都杉並区成田東2-33-12",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *に対し/wp-admin/のみDisallow"
                          "(admin-ajax.phpは例外的にAllow)。それ以外は制限なし)",
}

BASE_URL = "https://tamajicoffee.com"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(コーヒー豆単体の9セクションのみ対象)
TARGET_SECTIONS = {
    "軽くてソフト", "軽い中にも苦みと酸味", "酸味と苦みの良いバランス",
    "苦みとコク", "苦みとキレ", "カフェオレ専用", "エスプレッソ専用",
    "カフェインレス", "裏メニュー",
}

SECTION_PATTERN = re.compile(
    r'<h4>([^<]*(?:<span>[^<]*</span>)?)</h4>[\s\S]*?<div class="item_blocks clearfix">([\s\S]*?)</div>\s*<div class="btns">'
)
ITEM_PATTERN = re.compile(
    r'<a href="(https://tamajicoffee\.com/[^"]+)"[^>]*>[\s\S]*?'
    r'<div class="name">([^<]*)</div>[\s\S]*?<div class="pr">([^<]*)</div>'
)
PRICE_PATTERN = re.compile(r"([\d,]+)")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def scrape_catalog() -> list[dict]:
    """理由はモジュールdocstring参照(/online_shop/1ページに全カタログが
    埋め込まれているため、これを1回取得してセクションごとに解析する)。"""
    html = fetch_html(f"{BASE_URL}/online_shop/")
    results = []
    seen_urls = set()
    for section_m in SECTION_PATTERN.finditer(html):
        title = re.sub(r"<[^>]*>", "", section_m.group(1)).strip()
        if title not in TARGET_SECTIONS:
            continue
        block = section_m.group(2)
        for item_m in ITEM_PATTERN.finditer(block):
            product_url, raw_name, price_text = item_m.group(1), item_m.group(2).strip(), item_m.group(3)
            if product_url in seen_urls:
                continue
            seen_urls.add(product_url)

            price = None
            pm = PRICE_PATTERN.search(price_text)
            if pm:
                price = int(pm.group(1).replace(",", ""))

            results.append({"raw_name": raw_name, "product_url": product_url, "price": price})
    return results


def parse_item_content(soup: BeautifulSoup) -> dict[str, list[str]]:
    """div.item_content内のh5(ラベル)+p(値、複数可)の繰り返しを抽出する。
    理由はモジュールdocstring参照(原産国の値が複数ならブレンドの判定に使う)。"""
    container = soup.select_one("div.item_content")
    if not container:
        return {}
    fields: dict[str, list[str]] = {}
    current_label = None
    for child in container.find_all(["h5", "p"], recursive=False):
        if child.name == "h5":
            current_label = child.get_text(strip=True)
            fields[current_label] = []
        elif child.name == "p" and current_label:
            text = child.get_text(strip=True)
            if text:
                fields[current_label].append(text)
    return fields


def parse_altitude(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    normalized = text.replace(",", "")
    m = ALTITUDE_RANGE_PATTERN.search(normalized)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = ALTITUDE_SINGLE_PATTERN.search(normalized)
    if m:
        value = int(m.group(1))
        return value, value
    return None, None


def build_record(soup: BeautifulSoup, product_url: str, fallback_title: str, price: int | None) -> dict:
    title_el = soup.select_one("h3")
    # h3には商品コード(<span>A-1</span>)が併記されているため、商品名部分のみ取り出す
    raw_name = fallback_title
    if title_el:
        code_span = title_el.select_one("span")
        if code_span:
            code_span.extract()
        raw_name = title_el.get_text(strip=True) or fallback_title

    parsed = parse_product(raw_name)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_name,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    fields = parse_item_content(soup)
    # 理由はモジュールdocstring参照(原産国の複数値は、別々の<p>で並ぶ商品と、
    # 1つの<p>に「ジャマイカ、ブラジル」のようにカンマ区切りでまとめられる
    # 商品の2パターンがあることを実データで確認済み。「たまじブレンドJOKER」は
    # 後者のパターンで、<p>が1個しか無いためlen(origin_values)>1だけでは
    # ブレンドと判定できなかった不具合が実データ検証で判明したため、各値を
    # さらにカンマで分割してから個数を数える)
    origin_values = [
        part.strip()
        for raw in fields.get("原産国", [])
        for part in re.split(r"[、,]", raw)
        if part.strip()
    ]
    # 原産国が2件以上ならブレンド、1件なら単一原産地と判定できるが、季節限定
    # ブレンド等そもそも原産国欄が無い商品(0件)もあるため、その場合のみ商品名
    # 解析(parse_product)の「ブレンド」判定にフォールバックする(理由は
    # モジュールdocstring参照)
    if len(origin_values) >= 2:
        is_blend = True
    elif len(origin_values) == 1:
        is_blend = False
    else:
        is_blend = parsed["category"] == "ブレンド"
    parsed["category"] = "ブレンド" if is_blend else "ストレート"

    blend_components = []
    origin_country, origin_source = None, None
    processing_method = None
    if is_blend:
        for value in origin_values:
            country = detect_country_name(value)
            blend_components.append({"origin_country": country or value, "percentage": None})
    elif origin_values:
        country = detect_country_name(origin_values[0])
        if country:
            origin_country, origin_source = country, "product_description"
        else:
            origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]
    else:
        origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

    processing_values = fields.get("精製方法") or fields.get("プロセス")
    if processing_values and not is_blend:
        processing_method = normalize_processing_method(processing_values[0])

    region_values = fields.get("エリア") or fields.get("地域")
    region_detail = region_values[0] if region_values and not is_blend else None

    variety_values = fields.get("品種")
    variety = variety_values[0] if variety_values and not is_blend else None

    altitude_values = fields.get("標高")
    altitude_min, altitude_max = parse_altitude(altitude_values[0] if altitude_values else None)
    if is_blend:
        altitude_min, altitude_max = None, None

    roast_values = fields.get("おすすめロースト")
    roast_hint = roast_values[0] if roast_values else None

    stock_el = soup.select_one("div.item_stock")
    structural_out_of_stock = bool(stock_el) and "在庫有り" not in stock_el.get_text()
    stock_status = detect_stock_status(raw_name, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_name,
        "category": parsed["category"],
        "origin_country": origin_country if not is_blend else None,
        "origin_source": origin_source if not is_blend else None,
        "designated_brand": parsed["designated_brand"] if not is_blend else None,
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(受注焙煎のためroast_hintに保持)
        "roast_hint": roast_hint,
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": region_detail,
        "variety": variety,
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "blend_components": blend_components,
        "price": price,
        "weight_g": 100,  # 理由はモジュールdocstring参照(顧客向け表示単位を採用)
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_catalog()
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"], price=item["price"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(item["product_url"])
            detail = build_record(soup, item["product_url"], item["raw_name"], item["price"])
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")

    return records, flavored_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
        result = build_record(fetch_page(url), url, "", None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
        }
        with open("data_tamaji.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_tamaji.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
