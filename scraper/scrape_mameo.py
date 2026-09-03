# -*- coding: utf-8 -*-
"""
scrape_mameo.py

豆男珈琲(mameocoffee.base.shop)の商品情報を取得する。THE SHOP(BASE系)だが
NAGI COFFEE等のJSON-LDテーマとも、chouetteの「Relation」テーマとも異なる
「c-card」系の新しいBASEテーマ(実データ確認済み、2026-09時点)。

【店舗の実在・所在地について】
Google検索・Instagram(@mameocoffee、フォロワー4.2万人以上)で実在を確認済み
だが、公式サイトのlawページ(特定商取引法に基づく表記)には店舗独自の住所が
無く、ネットショップ作成サービスを提供するBASE株式会社自身の所在地が
記載されているのみだった(小規模個人事業主がBASEの「連絡先の省略」制度を
利用しているケースと見られる)。「ご注文をお受けしてから焙煎」という
受注焙煎モデルで、イベント出店も行っている(実データ確認済み: Instagram
投稿で「イベント出店のご依頼受付中」と明記)ことから、固定の実店舗を
持たないオンライン専業の可能性が高い。そのため店舗住所(address/prefecture)
は空のままにする(存在しない情報を推測しない)。

robots.txt確認済み(2026-09時点): NAGI COFFEE等と同一の記述(curl/
python-requests/aiohttp等の一般的なHTTPクライアントは個別にDisallow: /
指定があるが、User-agent: *ルールでは/cart/・/web_cart/・/shops/・
/api/shops/・違反報告ページ以外はAllow: /)。

【カテゴリが存在しない点について】
実データ確認済み: 本サイトには/categories/配下のカテゴリページが無く、
トップページに全24件の商品が直接一覧表示される(ページネーション無し)。
全件シングルオリジンで、ブレンド商品は現時点で無い。

【除外商品について】
全24件中「【選べるお試しセット 45g × 2種】自家焙煎コーヒー豆」の1件のみ、
2種類から選ぶアソート商品で特定の一豆を指さないため除外する
(NON_BEAN_KEYWORDS参照)。残り23件がシングルオリジンの実商品。

【商品詳細ページの説明文(meta descriptionと同一内容)について】
実データ確認済み(23件全件): p.p-item__summary内に、商品によっては
【LightRoast / 浅煎り】【DarkRoast / 中深煎り】等の焙煎度別テイスティング
コメント(星評価付き)が続いた後、「ー・ー・ー...」という区切り線を挟んで
【原産国 / Country】エチオピア / Ethiopia【地域 / Region】イルガチェフェ
イディド / Yirgacheffe, Idido【品種 / Variety】...【標高 / Altitude】...
【プロセス / Process】...(商品によっては【規格 / Grade】も)という
「日本語 / 英語」併記のラベル付き行が並ぶ。日本語(スラッシュの前)側のみを
採用する。

【焙煎度について(商品ごとに選択可否が異なる)】
実データ確認済み: 商品によって以下の2パターンがある。
  (A) 焙煎度セレクター(itemOption__nameが「焙煎度」)を持つ商品(例:
      「Ethiopia Wote Konga 2300 Natural」はLightRoast/DarkRoastの2択)。
      この場合はroast_level=None・roast_selectable=Trueとし、選択肢を
      roast_hintに保持する。
  (B) 焙煎度セレクターを持たず、商品名に単一の粗い焙煎度表記(浅煎り/
      中浅煎り/中深煎り等)が固定で埋め込まれている商品(例:「Ethiopia
      Yirgacheffe Idido Washed / 浅煎り100g」)。この場合はroast_selectable
      =Falseとし、商品名から抽出した粗い表記をroast_hintに保持する
      (プロ向け8段階表記ではないためroast_levelには反映しない)。

【在庫状態について】
実データ確認済み: 一覧ページのdiv.c-card__tag--endOfSale(テキスト
「SOLD OUT」)、詳細ページのdiv.p-item__tag.endOfSale(同テキスト)が
構造化された品切れシグナルとして機能している(24件中7件で確認)。

【価格・重量について】
実データ確認済み: 全商品が100gあたりの単価表示(例:「100g 〜」)で、
200g/300g/400g等はパッケージ説明文に「100gを複数パック」という形で
案内されているだけの数量倍数であり、別バリエーション価格は存在しない
(挽き方セレクターのみで、サイズセレクターは無い)。price/weight_gは
基本の100g単価をそのまま採用する。
"""

import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, normalize_processing_method, detect_stock_status, detect_country_name
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "豆男珈琲",
    "url": "https://mameocoffee.base.shop/",
    "platform": "THE SHOP(BASE系)",
    "address": None,
    "prefecture": None,
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE等と同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://mameocoffee.base.shop"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(2種から選ぶアソート商品で特定の一豆を指さない)
NON_BEAN_KEYWORDS = ["お試しセット"]

DETAIL_LABEL_PATTERN = re.compile(r"^【([^/】]+?)\s*/\s*[^】]*】\s*(.*)$")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~]\s*([\d,]+)\s*m")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*m")
# 粗い焙煎度表記(プロ向け8段階とは別)。「中浅煎り」等の複合語を「浅煎り」より
# 先にマッチさせるため長い語を先に並べる
ROAST_HINT_TERMS = ["中浅煎り", "中深煎り", "極深煎り", "浅煎り", "中煎り", "深煎り"]


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_weight(text: str) -> int | None:
    m = WEIGHT_PATTERN.search(unicodedata.normalize("NFKC", text or ""))
    return int(m.group(1)) if m else None


def parse_detail_fields(soup: BeautifulSoup) -> dict:
    """p.p-item__summary内の【ラベル / English】日本語値 / English値 という
    行を抽出する。理由はモジュールdocstring参照。"""
    summary_el = soup.select_one("p.p-item__summary")
    if not summary_el:
        return {}
    for br in summary_el.find_all("br"):
        br.replace_with("\n")

    fields: dict[str, str] = {}
    for line in summary_el.get_text().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = DETAIL_LABEL_PATTERN.match(line)
        if m:
            label = m.group(1).strip()
            value = m.group(2).split("/")[0].strip()
            fields[label] = value
    return fields


def parse_altitude(text: str | None) -> tuple[int | None, int | None]:
    if not text:
        return None, None
    normalized = unicodedata.normalize("NFKC", text).replace(",", "")
    m = ALTITUDE_RANGE_PATTERN.search(normalized)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = ALTITUDE_SINGLE_PATTERN.search(normalized)
    if m:
        value = int(m.group(1))
        return value, value
    return None, None


def find_roast_options(soup: BeautifulSoup) -> list[str]:
    for el in soup.select("div.itemOptionElement"):
        name_el = el.select_one("label.itemOption__name")
        if name_el and "焙煎" in name_el.get_text():
            options = []
            for opt in el.select("select option[value]"):
                text = opt.get_text(strip=True)
                if text and "選択" not in text:
                    options.append(text)
            return options
    return []


def find_roast_hint_in_title(title: str) -> str | None:
    for term in ROAST_HINT_TERMS:
        if term in title:
            return term
    return None


def build_record(soup: BeautifulSoup, product_url: str, fallback_title: str, price: int | None) -> dict:
    title_el = soup.select_one("h1.p-item__name-main")
    title = title_el.get_text(strip=True) if title_el else fallback_title

    tag_el = soup.select_one("div.p-item__tag.endOfSale")
    structural_out_of_stock = tag_el is not None

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

    fields = parse_detail_fields(soup)

    if fields.get("原産国"):
        country = detect_country_name(fields["原産国"])
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"

    processing_raw = fields.get("プロセス") or fields.get("精製")
    if processing_raw:
        parsed["processing_method"] = normalize_processing_method(processing_raw)

    parsed = apply_category_hint_fallback(parsed, fields.get("地域"))
    altitude_min, altitude_max = parse_altitude(fields.get("標高"))

    roast_options = find_roast_options(soup)
    if roast_options:
        roast_hint = "／".join(roast_options)
        roast_selectable = True
    else:
        roast_hint = find_roast_hint_in_title(title)
        roast_selectable = False

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
        "roast_level": None,  # 理由はモジュールdocstring参照(商品により選択式/固定式が混在)
        "roast_hint": roast_hint,
        "roast_selectable": roast_selectable,
        "post_processing_tags": parsed["post_processing_tags"],
        "region_detail": fields.get("地域"),
        "variety": fields.get("品種"),
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "blend_components": [],
        "price": price,
        "weight_g": parse_weight(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def scrape_top_page() -> list[dict]:
    soup = fetch_page(BASE_URL)
    results = []
    seen_urls = set()
    for card in soup.select("a.c-card"):
        href = card.get("href", "")
        if "/items/" not in href:
            continue
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)

        title_el = card.select_one("div.c-card__title")
        if not title_el:
            continue
        raw_name = title_el.get_text(strip=True)
        if any(kw in raw_name for kw in NON_BEAN_KEYWORDS):
            continue

        price = None
        price_el = card.select_one("div.c-card__price")
        if price_el:
            m = re.search(r"([\d,]+)", price_el.get_text())
            if m:
                price = int(m.group(1).replace(",", ""))

        results.append({"raw_name": raw_name, "product_url": product_url, "price": price})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items = scrape_top_page()
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
        with open("data_mameo.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_mameo.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
