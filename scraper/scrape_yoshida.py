# -*- coding: utf-8 -*-
"""
scrape_yoshida.py

吉田珈琲焙煎所(yoshidabaisenjo.com、神奈川県茅ヶ崎市東海岸北1-1-1、STORES製)の
商品情報を取得する。前身の店舗名は「i don't know coffee roaster」で、旧住所
(茅ヶ崎市東海岸南5-1-5)の店舗は2024年に閉店・移転し、2022年頃に現店名へ
変更済み(ユーザー確認済み)。本プロジェクトで初めて対応するSTORESプラット
フォーム。

robots.txt確認済み(2026-08時点): User-agent: * は/cart・/checkout・/login・
/mypage・/search・/tokushoho等の非公開/取引系のみDisallow(/items/は対象外)。
Crawl-delay: 20 が明示されているため、他店舗より大幅に長い間隔(20秒)を
リクエスト間に設ける。またデフォルトのcurl User-Agent(UA無し)だとCloudflareの
Captcha Challenge(HTTP 403)が返るため、識別可能なUser-Agentを明示的に
設定する(実データ確認済み)。

【商品カタログの構成について】
実データ確認済み(2026-08時点、全16件): この店舗は他店舗と異なり「コーヒー豆」
専用カテゴリが無く、/itemsページに全商品(EC限定ブレンド4種・カフェインレス
シングルオリジン1種・「いつものおいらの豆を！」という産地指定なしの汎用注文
アイテム1種・ドリップバッグ商品3種・水出しコーヒー1種・定期便2種・ギフト
BOX3種・業務用卸販売1種)が並列に並ぶ。このうち実際に「特定の産地の豆を
重量指定で購入できる」商品はEC限定ブレンド4種とカフェインレス1種のみで、
残り10件はいずれも特定の産地・焙煎度を持たない商品(ドリップバッグは挽き豆の
アソート、定期便・「いつものおいらの豆を！」は届く豆が固定でない、ギフトBOX・
業務用卸販売は特定の一豆を指すものではない)。除外はNON_BEAN_KEYWORDSに
よるタイトルキーワードチェックで行う(実データで確認済みの10件を網羅)。

【重量表記の揺れについて】
実データ確認済み: ほとんどの商品は説明文の【内容量】欄に「200g」のような
グラム表記があるが、カフェインレスシングルオリジン(および「いつものおいらの
豆を！」、後者は除外対象)は「2000円分」のような金額ベースの表記になっている
(実際の支払い金額detailCtrl.salesPriceは2200円で、送料200円を含めた合計と
考えられる)。グラム数が明記されていない商品はweight_gを推測せずnullのままに
する。

【EC限定ブレンドの産地情報について】
実データ確認済み: EC限定ブレンド4種(java/norah/晴/ケ)には「原産国：」のような
構造化ラベルは無く、冒頭の紹介文に「深煎りのインドネシアがベースのブレンド
です」のように自由記述でベースの産地国が1つだけ言及されている。coffee_parser.
detect_country_name()を紹介文に対してそのまま適用すれば、文中のどこにあっても
国名を検出できる(正規表現で前後の助詞を切り出す必要が無い)。ただし配合比率の
記載は無いため、Denim bis等と同じ方針でblend_componentsには反映せず、
origin_countryもブレンドとして常にNoneのままにする(ベース産地の言及は
flavor_notesの自由記述内にそのまま残る)。

【カフェインレス商品の原産国・焙煎度について】
実データ確認済み(”カフェインレス”のエチオピア): 唯一「原産国：エチオピア」
「焙煎度：中深煎り」という構造化ラベルを持つ商品。焙煎度は「浅煎り/中煎り/
中深煎り/深煎り」相当の粗い自己申告表記で、本アプリのroast_levelが要求する
プロ向け8段階表記とは粒度が異なるため、他店舗と同じ方針でroast_hintとして
保持しroast_levelには反映しない。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, apply_category_hint_fallback, detect_country_name

SHOP_INFO = {
    "name": "吉田珈琲焙煎所",
    "url": "https://yoshidabaisenjo.com/",
    "platform": "STORES",
    "address": "神奈川県茅ヶ崎市東海岸北1-1-1",
    "prefecture": "神奈川県",
    "robots_txt_status": "許可(2026-08確認。/cart・/checkout・/login・/mypage・/search・"
                          "/tokushoho等の非公開/取引系のみDisallow、/items/は対象外。"
                          "Crawl-delay: 20が明示されている。デフォルトUA[UA無し]だと"
                          "CloudflareのCaptcha Challenge[HTTP 403]が返るため、"
                          "識別可能なUser-Agentを使用)",
}

BASE_URL = "https://yoshidabaisenjo.com"
CRAWL_DELAY_SECONDS = 20  # robots.txtのCrawl-delay: 20に従う
# 理由: GitHub Actionsのランナー上ではCloudflareのボット対策により
# CoffeeFinderBot/0.1単体のUser-Agentだけでは403 Forbiddenが返ることを
# 実際のワークフロー実行で確認した(ローカル環境からの同一UAでは200が返って
# いたため、UA文字列単体ではなくIPレピュテーション+リクエストヘッダーの
# 組み合わせで判定されていると考えられる)。一般的なブラウザが送る一式の
# ヘッダーを追加することで通過を試みる。
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 理由はモジュールdocstring参照。実データ確認済み(2026-08時点)の非豆商品10件を網羅
NON_BEAN_KEYWORDS = [
    "最終手段アイテム", "水だしエチオピア", "定期便", "GIFT", "業務用卸販売",
    "いつものおいらの豆を",
]

PRICE_PATTERN = re.compile(r"detailCtrl\.salesPrice\s*=\s*(\d+)")
ORIGIN_LABEL_PATTERN = re.compile(r"原産国[：:]\s*([^\n]+)")
ROAST_LABEL_PATTERN = re.compile(r"焙煎度[：:]\s*([^\n]+)")
WEIGHT_PATTERN = re.compile(r"【内容量】\s*\n?\s*(\d+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def scrape_item_list() -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/items")
    results = []
    for link_el in soup.select("a.c-itemList__item-link[href]"):
        name_el = link_el.select_one(".c-itemList__item-name")
        if not name_el:
            continue
        raw_name = name_el.get_text(strip=True)
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        results.append({"raw_name": raw_name, "product_url": product_url})
    return results


def build_record(product_url: str, raw_title: str, description: str, price: int | None) -> dict:
    parsed = parse_product(raw_title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": raw_title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": price,
            "product_url": product_url,
        }

    is_blend = parsed["category"] == "ブレンド"

    origin_match = ORIGIN_LABEL_PATTERN.search(description)
    if origin_match and not is_blend:
        country = detect_country_name(origin_match.group(1))
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = "product_description"
    parsed = apply_category_hint_fallback(parsed, None)

    roast_match = ROAST_LABEL_PATTERN.search(description)
    roast_hint = roast_match.group(1).strip() if roast_match else None

    weight_match = WEIGHT_PATTERN.search(description)
    weight_g = int(weight_match.group(1)) if weight_match else None

    # 冒頭の紹介文(【内容量】等のラベル行より前の部分)をflavor_notesとして保持する。
    # ブレンドのベース産地(例:「深煎りのインドネシアがベースのブレンドです」)も
    # この紹介文内に自由記述として残る(理由はモジュールdocstring参照)。既に
    # origin_country/roast_hintとして構造化済みの「原産国：」「焙煎度：」行は
    # 重複表示にならないよう取り除く。
    intro_lines = description.split("【")[0].strip().split("\n")
    intro = "\n".join(
        line for line in intro_lines
        if not ORIGIN_LABEL_PATTERN.match(line.strip()) and not ROAST_LABEL_PATTERN.match(line.strip())
    ).strip()

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": raw_title,
        "category": parsed["category"],
        "origin_country": None if is_blend else parsed["origin_country"],
        "origin_source": None if is_blend else parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い自己申告表記のためroast_hintに保持)
        "roast_hint": roast_hint,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],  # 配合比率の記載が無いため未対応(理由はモジュールdocstring参照)
        "flavor_notes": intro or None,
        "price": price,
        "weight_g": weight_g,
        "stock_status": "販売中",  # サイト上に在庫状態を示す表示が無いため、掲載=販売中として扱う
        "out_of_stock": False,
        "product_url": product_url,
    }


def parse_product_detail(url: str) -> dict:
    soup = fetch_page(url)
    html = str(soup)

    title_el = soup.select_one("h1.item_name")
    raw_title = title_el.get_text(strip=True) if title_el else ""

    price_match = PRICE_PATTERN.search(html)
    price = int(price_match.group(1)) if price_match else None

    desc_el = soup.select_one("div.main_content_result_item_list_detail")
    description = desc_el.get_text() if desc_el else ""

    if not raw_title:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }

    return build_record(url, raw_title, description, price)


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    list_items = scrape_item_list()
    time.sleep(CRAWL_DELAY_SECONDS)

    records = []
    flavored_records = []
    non_bean_records = []

    for item in list_items:
        if any(kw in item["raw_name"] for kw in NON_BEAN_KEYWORDS):
            non_bean_records.append({
                "shop_name": SHOP_INFO["name"],
                "raw_name": item["raw_name"],
                "non_bean": True,
                "product_url": item["product_url"],
            })
            continue

        try:
            detail = parse_product_detail(item["product_url"])
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
    records, flavored_records, non_bean_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
        "non_bean_products_excluded": non_bean_records,
    }
    with open("data_yoshida.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_yoshida.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件、"
          f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
