# -*- coding: utf-8 -*-
"""
scrape_nericafe.py

nericafe(ネリカフェ、nericafe.com、東京都練馬区大泉学園)の商品情報を取得する。
カラーミーショップ(shop-pro.jp)。scrape_kunikuni.py・scrape_405coffee.py等と
同じプラットフォームだが、テーマは異なる(li.prd_lst_unit、商品説明は
og:descriptionに【ラベル】値形式で埋め込み)。

robots.txt確認済み(2026-09時点): User-agent: *は/secure/・/cart/のみ制限。
AhrefsBot/DotBot等の特定クローラーのみ個別に全面Disallowだが、本スクレイパーは
識別可能な独自User-Agentを使用するため該当しない。

【文字コード】EUC-JP(実データ確認済み、Content-Type: text/html; charset=euc-jp)。
kunikuni.py等と同じくrequestsの自動判定に頼らずresp.encodingを明示する。

【対象カテゴリについて】
トップページのカテゴリ一覧のうち「フィルター器具」(1967566、器具)・
「実店舗のご案内」(2150361、店舗情報)は明確に非コーヒー豆のため除外。
「浅煎りのコーヒー豆」(2847347)・「深煎りのコーヒー豆」(2847348)・
「中〜中深煎りのコーヒー豆」(2847349)の3カテゴリ(焙煎度別、和集合8件)が
コーヒー豆全件を指す。

【商品説明(og:description)の構造について】
実データ確認済み(8件全件): 「【焙煎度合】浅煎り【生産地】...【標  高】...
【精  製】...【品  種】...<フリーテキストのテイスティングノートが続く>」という
形式で、ラベルとラベルの間に改行が無く連結されている。また「標　高」
「精　製」「品　種」のように一部ラベルの2文字の間に全角スペースが入っている
表記ゆれがあるため、ラベル抽出時は空白を除去してから既知のラベル名と照合する。
最後のラベル(品種)の値はテイスティングノートのフリーテキストとの境界が
無いため汚染される(次の【】が来るまでを値として拾ってしまう)。信頼できない
ため品種はvarietyとして出力しない(スコープ外とする)。

【生産地ラベルとブレンド判定について】
実データ確認済み: 「スペシャルナチュラルモカ100g」(pid=187067246)は商品名に
「ブレンド」を含まないが、【生産地】が「エチオピア、イエメン」と2カ国
列挙されており、一覧ページの説明文にも「エチオピアにイエメンをブレンド」と
明記されている(実質ブレンド商品)。他の7件は【生産地】に国名が1つしか
現れない単一原産地。たまじ珈琲・MARUTAKE COFFEE BEANSと同じ「構造化データが
商品名テキストより優先」の方針を踏襲し、【生産地】を「、」区切りで分割して
各断片からdetect_country_name()で国名を検出し、判明した国の数で
ブレンド/ストレートを判定する(0件の場合のみ商品名解析にフォールバック)。

【焙煎度合について】
【焙煎度合】の値は「浅煎り」「中煎り」等の粗い3〜4段階表記でプロ向け8段階
表記(ROAST_KEYWORDS)と粒度が異なるため、MARUTAKE COFFEE BEANSと同じく
roast_hintとして保持しroast_levelには反映しない。

【精製方法のシノニム追加について】
実データ確認済み: 【精  製】欄が「水洗式」「自然乾燥式」という漢字表記で、
従来のカタカナ表記(ウォッシュド/ナチュラル)シノニム辞書に無かったため、
data/processing_method_synonyms.jsonへ両表記を追加した(意味が一意に
定まる直訳表現であり誤爆リスクが無いため)。

【重量・価格・在庫について】
実データ確認済み: 商品名末尾に必ず「100g」を含み全商品が100g単品のみ
(重量バリエーション無し)。var Colormeオブジェクトの
variants は「豆のまま」「粉状に挽く」という挽き方の選択肢のみで重量は
変わらないため、価格はproduct.sales_price_including_taxをそのまま採用する。
inventory_controlが"option"(=在庫管理が機能している。kunikuniの"none"とは
異なる)であることを実データ確認済みのため、product.stock_numを構造化された
在庫フラグとして利用する。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    apply_category_hint_fallback,
    detect_country_name,
    normalize_processing_method,
    detect_stock_status,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "nericafe",
    "url": "https://nericafe.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "東京都練馬区大泉学園",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。User-agent: *は/secure/・/cart/のみ制限。"
                          "AhrefsBot等の特定クローラーは個別に全面Disallowだが、"
                          "本スクレイパーは識別可能な独自User-Agentを使用)",
}

BASE_URL = "https://nericafe.com"
# 理由はモジュールdocstring参照(焙煎度別3カテゴリの和集合がコーヒー豆全件)
LIST_CATEGORIES = {
    "2847347": "浅煎り",
    "2847348": "深煎り",
    "2847349": "中〜中深煎り",
}
CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
LABEL_PATTERN = re.compile(r"【(.+?)】")
WEIGHT_PATTERN = re.compile(r"(\d+)\s*[gｇ]")
ALTITUDE_RANGE_PATTERN = re.compile(r"([\d,]+)\s*[-〜~－]\s*([\d,]+)\s*[mｍ]")
ALTITUDE_SINGLE_PATTERN = re.compile(r"([\d,]+)\s*[mｍ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=euc-jp)
    return BeautifulSoup(resp.text, "html.parser")


def extract_colorme_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        m = COLORME_JSON_PATTERN.search(text)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return None
        return data.get("product")
    return None


def parse_description_fields(description: str) -> dict:
    """理由はモジュールdocstring参照(ラベル間に改行が無く連結されているため、
    次の【】が現れる位置までを値として切り出す。ラベル自体は空白を除去して
    正規化する)。"""
    matches = list(LABEL_PATTERN.finditer(description or ""))
    fields: dict[str, str] = {}
    for i, m in enumerate(matches):
        label = re.sub(r"\s+", "", m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(description)
        fields[label] = description[start:end].strip()
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


def parse_weight_from_title(title: str) -> int | None:
    m = WEIGHT_PATTERN.search(title or "")
    return int(m.group(1)) if m else None


def build_record(product_url: str, colorme_product: dict, description: str, category_hint: str) -> dict:
    title = (colorme_product.get("name") or "").strip()
    parsed = parse_product(title)

    price = colorme_product.get("sales_price_including_tax")

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

    fields = parse_description_fields(description)

    origin_raw = fields.get("生産地")
    origin_countries: list[str] = []
    if origin_raw:
        for part in re.split(r"[、,]", origin_raw):
            country = detect_country_name(part)
            if country and country not in origin_countries:
                origin_countries.append(country)

    # 理由はモジュールdocstring参照(【生産地】で判明した国の数を優先し、
    # 0件の場合のみ商品名解析(parse_product)の判定にフォールバックする)
    if len(origin_countries) >= 2:
        is_blend = True
    elif len(origin_countries) == 1:
        is_blend = False
    else:
        is_blend = parsed["category"] == "ブレンド"
    parsed["category"] = "ブレンド" if is_blend else "ストレート"

    blend_components = []
    origin_country, origin_source = None, None
    if is_blend:
        blend_components = [{"origin_country": c, "percentage": None} for c in origin_countries]
    else:
        if origin_countries:
            origin_country, origin_source = origin_countries[0], "product_description"
        else:
            origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

    parsed = apply_category_hint_fallback(parsed, category_hint if not origin_country else None)
    if not origin_country:
        origin_country, origin_source = parsed["origin_country"], parsed["origin_source"]

    processing_method = None
    processing_raw = fields.get("精製")
    if processing_raw:
        processing_method = normalize_processing_method(processing_raw)
    elif parsed["processing_method"]:
        processing_method = parsed["processing_method"]

    altitude_min, altitude_max = parse_altitude(fields.get("標高"))

    structural_out_of_stock = (colorme_product.get("stock_num") or 0) <= 0
    stock_status = detect_stock_status(title, structural_out_of_stock)

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "category_hint": category_hint,
        "origin_country": origin_country,
        "origin_source": origin_source,
        "designated_brand": parsed["designated_brand"],
        "processing_method": processing_method,
        "grade": parsed["grade"],
        "roast_level": None,  # 理由はモジュールdocstring参照(粗い焙煎度表記のためroast_hintに保持)
        "roast_hint": fields.get("焙煎度合"),
        "post_processing_tags": parsed["post_processing_tags"],
        "altitude_min_m": altitude_min,
        "altitude_max_m": altitude_max,
        "blend_components": blend_components,
        "price": price,
        "weight_g": parse_weight_from_title(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    colorme_product = extract_colorme_product(soup)
    if not colorme_product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    meta_desc = soup.select_one('meta[property="og:description"]')
    description = meta_desc.get("content", "") if meta_desc else ""
    return build_record(url, colorme_product, description, category_hint)


def scrape_category_list(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/?mode=cate&cbid={cid}&csid=0")
    results = []
    for item in soup.select("li.prd_lst_unit"):
        title = None
        href = None
        for link in item.select('a[href*="pid="]'):
            text = link.get_text(strip=True)
            if text:
                title = text
                href = link.get("href", "")
                break
        if not title or not href:
            continue
        product_url = f"{BASE_URL}/{href}" if href.startswith("?") else href
        results.append({"raw_name": title, "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list(cid):
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
        with open("data_nericafe.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_nericafe.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
