# -*- coding: utf-8 -*-
"""
scrape_beanstei.py

びーんず亭(beanstei.com、京都市中京区・錦市場)の商品情報を取得する。
EC-CUBE(オープンソースの日本製ECプラットフォーム)というこのプロジェクト
初対応のプラットフォーム。ECSESSIDというEC-CUBE固有のセッションCookie名で
プラットフォームを特定した(実データ確認済み、2026-09時点)。

robots.txt確認済み(2026-09時点): User-agent: *に対し、特定のクエリパラメータ
(?category_id=48=を含むURL、フィルタ検索のバリエーション対策とみられる)
のみDisallowで、それ以外は制限なし。本スクレイパーが使用する商品一覧
(/products/list.php?category_id=)・商品詳細(/products/detail.php?product_id=)
はいずれもDisallow対象に含まれない。

【対象カテゴリについて】
「ブレンド豆」(category_id=7、10件)・「ストレート豆」(category_id=8、13件)
を対象とする(計23件、いずれもページネーション無し)。「生豆」(9)・
「コーヒーギフト」(10)・「コーヒーセット」(11)は対象外。

【商品詳細ページの説明文(main_comment)について】
実データ確認済み: ストレート豆の説明文(div.main_comment)冒頭に
「原産国:エチオピア連邦民主共和国」「生産地区:シダモ地方イルガチェフェ地区」
「標高約1,800～2,000m」「精製方法:ウォッシュド」「品種:在来種のグレード2」
という行が並ぶことが多いが、書式に一貫性が無い(実データ確認済み: ある商品
(id=109)では「生産地区:標高約1,300～1,800m」のように標高がラベルごと
誤ったラベルの値として書かれている一方、別の商品(id=296)では「標高:約1,300m」
と正しくラベル化されている)。この揺れに対応するため、標高は特定のラベル値
としてではなく、ヘッダー部分のテキスト全体から「標高」を含む行を正規表現で
直接検索して抽出する(parse_altitude参照)。ブレンド豆・カフェインレス豆には
この構造化ラベルが無い商品もあり(実データ確認済み: 「カフェインレス
コロンビア」はデカフェ加工方法の説明のみで原産国ラベル自体が無い)、
ラベルが無い場合は商品名からの産地判定にフォールバックする。

【カテゴリを「ブレンド/ストレート」の判定に使う理由】
実データ確認済み: 「プレミアムアイス」「びーんず亭フルロースト」のように
商品名に「ブレンド」を含まないブレンド商品が複数あり(10件中2件)、商品名
解析だけではブレンド判定が不安定。カテゴリ一覧のcategory_id(7=ブレンド豆/
8=ストレート豆)を一次情報としてcategoryを決定する。

【デカフェ処理方法について】
実データ確認済み(id=16「カフェインレス　コロンビア」): 説明文に
「スイスウォータープロセス」という具体的なデカフェ加工方法名が記載されている
一方、原産国・精製方法・品種等の構造化ラベルは無い。商品名に「カフェインレス」
「デカフェ」を含む場合のみ、既知のデカフェ加工方法名を説明文から検索する
(DECAF_PROCESS_PATTERN参照)。

【内容量・価格について】
実データ確認済み(23件全件): 全商品が例外なく100g/価格の単位表示
(div.naiyouryouの「内容量：100g」、価格欄の「¥XXX/100g」)。weight_gは
div.naiyouryouの値をそのまま採用する。

【在庫状態について】
実データ確認済み: 商品ステータス表示欄(コメントアウト前後に囲まれた領域)は
売り切れ商品を含めて常に空で、構造化された品切れシグナルが機能していない
ことを確認した(「完売」等のテキストは無関係な「関連商品」ウィジェット内に
現れることがあり、対象商品自身の状態を示すとは限らない)。そのため商品名の
テキストマーカーのみで判定する(coffee_parser.detect_stock_status)。
"""

import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method, detect_stock_status, detect_country_name
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "びーんず亭",
    "url": "https://www.beanstei.com/",
    "platform": "EC-CUBE",
    "address": "京都府京都市中京区高倉通錦小路下ル中魚屋町511",
    "prefecture": "京都府",
    "robots_txt_status": "実質許可(2026-09確認。特定のクエリパラメータ(?category_id=48=系)のみ"
                          "Disallow、それ以外はUser-agent: *に制限なし)",
}

BASE_URL = "https://www.beanstei.com"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(コーヒー豆単品の2カテゴリのみ対象)
LIST_CATEGORIES = {
    "7": "ブレンド豆",
    "8": "ストレート豆",
}

LABEL_PATTERN = re.compile(r"^(.+?)[:：]\s*(.+)$")
ALTITUDE_RANGE_PATTERN = re.compile(r"標高[^\d]*([\d,]+)\s*[-〜~～]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"標高[^\d]*([\d,]+)\s*m")
DECAF_PROCESS_PATTERN = re.compile(r"(スイスウォータープロセス|マウンテンウォータープロセス|"
                                    r"エチルアセテート(?:プロセス)?|CO2(?:プロセス)?)")
PRICE_PATTERN = re.compile(r"([\d,]+)")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_altitude(text: str) -> tuple[int | None, int | None]:
    """理由はモジュールdocstring参照(ラベルの誤記揺れがあるため、ヘッダー部分の
    テキスト全体から「標高」を含む箇所を直接検索する)。"""
    normalized = text.replace(",", "")
    m = ALTITUDE_RANGE_PATTERN.search(normalized)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = ALTITUDE_SINGLE_PATTERN.search(normalized)
    if m:
        value = int(m.group(1))
        return value, value
    return None, None


def parse_description_fields(comment_text: str) -> tuple[dict, int | None, int | None]:
    """main_commentのヘッダー部分(空行まで)を「ラベル:値」形式で抽出する。
    理由はモジュールdocstring参照。"""
    lines = comment_text.split("\n")
    header_lines: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            break
        header_lines.append(line)
    header_text = "\n".join(header_lines)

    fields: dict[str, str] = {}
    for line in header_lines:
        m = LABEL_PATTERN.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()

    altitude_min, altitude_max = parse_altitude(header_text)
    return fields, altitude_min, altitude_max


def build_record(item: dict, soup: BeautifulSoup) -> dict:
    title_el = soup.select_one("div.detail_product_name h3")
    title = title_el.get_text(strip=True) if title_el else item["raw_name"]

    is_blend = item["category_hint"] == "ブレンド豆"
    parsed = parse_product(title)
    if is_blend:
        parsed["category"] = "ブレンド"

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": item.get("price"),
            "product_url": item["product_url"],
        }

    comment_el = soup.select_one("div.main_comment")
    comment_text = comment_el.get_text(separator="\n", strip=True) if comment_el else ""
    fields, altitude_min, altitude_max = parse_description_fields(comment_text)

    is_decaf = "カフェインレス" in title or "デカフェ" in title
    decaf_process = None
    if is_decaf:
        m = DECAF_PROCESS_PATTERN.search(comment_text)
        if m:
            decaf_process = m.group(1)

    origin_country, origin_source = None, None
    processing_method = None
    variety = None
    region_detail = None
    if not is_blend:
        origin_label = fields.get("原産国")
        if origin_label:
            country = detect_country_name(origin_label)
            if country:
                origin_country, origin_source = country, "product_description"
        if not origin_country and parsed["origin_country"]:
            origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

        processing_raw = fields.get("精製方法")
        if processing_raw:
            processing_method = normalize_processing_method(processing_raw)

        variety = fields.get("品種")

        # 「生産地区」の値が標高の誤記載でない場合のみ地域情報として採用する
        # (理由はモジュールdocstring参照)
        region_raw = fields.get("生産地域") or fields.get("生産地区")
        if region_raw and "標高" not in region_raw:
            region_detail = region_raw

    parsed["origin_country"] = origin_country
    parsed["origin_source"] = origin_source
    parsed = apply_category_hint_fallback(parsed, item["category_hint"])

    weight_g = None
    naiyouryou_el = soup.select_one("div.naiyouryou div.detail_right")
    if naiyouryou_el:
        m = re.search(r"(\d+)", naiyouryou_el.get_text())
        if m:
            weight_g = int(m.group(1))

    stock_status = detect_stock_status(title)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": item["category_hint"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": None if is_blend else processing_method,
        "grade": parsed["grade"],
        "roast_level": parsed["roast_level"],
        "post_processing_tags": parsed["post_processing_tags"],
        "variety": None if is_blend else variety,
        "region_detail": None if is_blend else region_detail,
        "altitude_min_m": None if is_blend else altitude_min,
        "altitude_max_m": None if is_blend else altitude_max,
        "decaf_process": decaf_process,
        "blend_components": [],
        "price": item.get("price"),
        "weight_g": weight_g,
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


def scrape_category_list(cid: str, category_hint: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/products/list.php?category_id={cid}")
    results = []
    seen_urls = set()
    for form in soup.select('form[name^="product_form"]'):
        title_el = form.select_one("h3.product_name a")
        if not title_el:
            continue
        href = title_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        price = None
        price_el = form.select_one("div.product_price span.price")
        if price_el:
            m = PRICE_PATTERN.search(price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        results.append({
            "raw_name": title_el.get_text(strip=True),
            "product_url": product_url,
            "price": price,
            "category_hint": category_hint,
        })
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid, category_hint):
            items_by_url.setdefault(item["product_url"], item)
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"], price=item["price"]):
            records.append(prev)
            continue

        try:
            soup = fetch_page(product_url)
            detail = build_record(item, soup)
            if detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records


def main():
    import json

    records, flavored_records = scrape_all_products()

    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    with open("data_beanstei.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[done] {len(records)}件を data_beanstei.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")


if __name__ == "__main__":
    main()
