# -*- coding: utf-8 -*-
"""
scrape_himonya.py

HIMONYA FIVE COFFEE(shop.himonyafivecoffee.com、東京都目黒区)の商品情報を取得する。
THE SHOP(BASE系)。NAGI COFFEE・FINETIME COFFEE ROASTERS・珈琲家あのころと同じ
JSON-LD構造化データを持つテーマ(items-grid_*系のハッシュ付きクラス名)。

robots.txt確認済み(2026-09時点): NAGI COFFEE等と同一の記述(curl/python-requests/
aiohttp等の一般的なHTTPクライアントは個別にDisallow: /指定があるが、
User-agent: *ルールでは/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ
以外はAllow: /)。本スクレイパーが使用する商品詳細ページ(/items/)・カテゴリ
一覧ページ(/categories/)はいずれもDisallow対象に含まれない。

【対象カテゴリについて】
ユーザー指定のcategories/5845012(コーヒー豆・ブレンド、9件)・
categories/5845011(コーヒー豆・シングルオリジン、24件)を対象とする(計33件、
いずれもページネーション無し)。「ナッツ類」(5845014)・「コーヒー１杯ドリップ」
(5845016)・「水出しコーヒー＆MILK BREW」(6806825)はこの2カテゴリに含まれず、
除外用のキーワード処理は不要だった。

【「生豆」表記について(実データ確認済み、2026-09時点、重要)】
本サイトの全33商品の商品名には例外なく「(生豆240g)」または「(生豆600g)」という
表記が付いている。一見、焙煎前の生豆をそのまま販売しているように見えるが、
商品説明文に「内容量：生豆240gを焙煎し、焙煎後は約200gとなります」(600gの場合は
「焙煎後は約500g」)と明記されており、実際には焙煎度合セレクター(後述)で選んだ
焙煎度で店側が焙煎してから発送する「受注焙煎」方式であることを確認した(未焙煎の
生豆をそのまま発送する意図ではない)。そのため本アプリのweight_gには商品名の
生豆重量(240g/600g)ではなく、説明文に明記された焙煎後の実重量(約200g/約500g)を
採用する(WEIGHT_ROASTED_PATTERN参照)。raw_nameは商品名をそのまま保持する。

【商品説明文(JSON-LD description)の構造について】
実データ確認済み(33件全件): 冒頭に以下の「ラベル：値」形式の行が4行並び、
空行を挟んで自由記述のテイスティングコメントが続く。
  原産国：<国名>(ブレンドは「（ブレンド）」という固定値)
  製法・配合：<精選方法>(ブレンドは「〇〇ブレンド」というブレンド名で、
    精選方法としては扱えない)
  お奨め焙煎度：<自由記述>(「すべて」「マイルド」「やや浅煎り〜マイルド」等、
    プロ向け8段階表記ではない粗い推奨表現)
  内容量：生豆<N>gを焙煎し、焙煎後は約<M>gとなります
自由記述部分は新しい商品ほど「テイストプロフィール」(フレーバー/酸味/ボディ/
アフターテイスト)や「焙煎度別おすすめコメント」を含む長文になっているが、
古い商品は1〜2文の短い紹介文のみ(構造化の程度が商品によって一貫しない)。
flavor_notesは「フレーバー：」行があればその値を、無ければ自由記述の先頭段落を
採用する(parse_description参照)。

【原産国の判定について(商品名だけでは判定できない実データ多数)】
実データ確認済み: 「ゴリ ゲシャ」「リベリカ プレミアム タイガー」「ンベサ村の
ピーベリー」「ダイヤモンドマウンテン ラ・エスメラルダ農園」「エメラルドマウンテン」
「カスティージョ」のように、商品名に国名を一切含まない商品が多数ある一方、
「原産国：」欄には必ず正しい国名(コロンビア・マレーシア・カメルーン・パナマ等)が
明記されている。そのため商品名からのcoffee_parser.parse_product()の産地判定
(特定銘柄のみ、ブルーマウンテンNo.1・ハワイコナEXファンシー等で機能する)を
優先しつつ、判定できなかった場合は必ず「原産国：」欄を一次情報として採用する
(Muiのtable.info-tableと同じ発想)。

【ブレンドの判定について(商品名だけでは判定できない実データ多数)】
実データ確認済み: ブレンド9件のうち「エチオピアブレンド」「AKO'sブレンド」の
2件のみ商品名に「ブレンド」を含み、残り7件(「新カリブの恋人」「碑文谷スペシャル」
「エスプレッソ５」等)は商品名だけでは判定できない。特に「エチオピアブレンド」は
商品名に国名「エチオピア」を含むため、商品名解析だけに頼るとブレンドなのに
単一原産地(エチオピア)と誤判定してしまう(実データで「原産国：（ブレンド）」と
明記されていることを確認済み)。そのため、ブレンド判定は商品名ではなく
「原産国：」欄の値が「（ブレンド）」であるかどうかで行う(is_blend参照)。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import parse_product, detect_country_name, normalize_processing_method, detect_stock_status
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "HIMONYA FIVE COFFEE",
    "url": "https://shop.himonyafivecoffee.com/",
    "platform": "THE SHOP(BASE系)",
    "address": "東京都目黒区碑文谷5-11-6",
    "prefecture": "東京都",
    "robots_txt_status": "実質許可(2026-09確認。NAGI COFFEE等と同一の記述。"
                          "/cart/・/web_cart/・/shops/・/api/shops/・違反報告ページ以外はUser-agent: *でAllow。"
                          "curl/python-requests等は個別にDisallow: /指定あり、"
                          "本スクレイパーは識別可能なUser-Agentを使用)",
}

BASE_URL = "https://shop.himonyafivecoffee.com"
CRAWL_DELAY_SECONDS = 2
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

# 理由はモジュールdocstring参照(ユーザー指定の2カテゴリ、いずれもコーヒー豆専用)
LIST_CATEGORIES = {
    "5845012": "ブレンド",
    "5845011": "シングルオリジン",
}

LABEL_PATTERN = re.compile(r"^(.+?)[：:]\s*(.*)$")
FLAVOR_LINE_PATTERN = re.compile(r"^-?\s*フレーバー[：:]\s*(.+)$")
WEIGHT_ROASTED_PATTERN = re.compile(r"焙煎後は約\s*([\d.]+)\s*[gｇ]")


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def extract_jsonld_product(soup: BeautifulSoup) -> dict | None:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            return data
    return None


def parse_description(description: str) -> tuple[dict, str | None]:
    """理由はモジュールdocstring参照。冒頭の「ラベル：値」行のブロックを空行まで
    抽出し、残りの自由記述から「フレーバー：」行(あれば)または先頭段落を
    flavor_notesとして採用する。"""
    lines = (description or "").split("\n")
    fields: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            break
        m = LABEL_PATTERN.match(line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()
        i += 1

    remaining = lines[i:]
    flavor_notes = None
    for line in remaining:
        m = FLAVOR_LINE_PATTERN.match(line.strip())
        if m:
            flavor_notes = m.group(1).strip()
            break

    if not flavor_notes:
        paragraph: list[str] = []
        for line in remaining:
            line = line.strip()
            if not line:
                if paragraph:
                    break
                continue
            paragraph.append(line)
        flavor_notes = "".join(paragraph) if paragraph else None

    return fields, flavor_notes


def parse_roasted_weight(description: str) -> int | None:
    m = WEIGHT_ROASTED_PATTERN.search(description or "")
    return int(float(m.group(1))) if m else None


def build_record(product_url: str, product: dict, category_hint: str) -> dict:
    title = (product.get("name") or "").strip()
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        offers = product.get("offers") or {}
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": int(offers["price"]) if offers.get("price") else None,
            "product_url": product_url,
        }

    description = product.get("description") or ""
    fields, flavor_notes = parse_description(description)
    origin_label = fields.get("原産国")

    # 理由はモジュールdocstring参照(商品名の「ブレンド」有無ではなく、
    # 「原産国：（ブレンド）」の構造化表記で判定する)
    is_blend = bool(origin_label) and "ブレンド" in origin_label
    if is_blend:
        parsed["category"] = "ブレンド"

    if is_blend:
        origin_country = None
        origin_source = None
        processing_method = None
    elif parsed["designated_brand"]:
        # 特定銘柄(ハワイコナ・ブルーマウンテン等)は商品名解析の判定を優先する
        # (coffee_parser.DESIGNATED_BRAND_KEYWORDSが持つ正規化済みの値を信頼する)
        origin_country = parsed["origin_country"]
        origin_source = parsed["origin_source"]
        processing_raw = fields.get("製法・配合")
        processing_method = normalize_processing_method(processing_raw) if processing_raw else None
    else:
        country = detect_country_name(origin_label) if origin_label else None
        if country:
            origin_country = country
            origin_source = "product_description"
        elif parsed["origin_country"]:
            origin_country = parsed["origin_country"]
            origin_source = parsed["origin_source"]
        else:
            origin_country = origin_label or None
            origin_source = "product_description" if origin_label else None
        processing_raw = fields.get("製法・配合")
        processing_method = normalize_processing_method(processing_raw) if processing_raw else None

    offers = product.get("offers") or {}
    price = int(offers["price"]) if offers.get("price") else None
    availability = offers.get("availability") or ""
    structural_out_of_stock = "InStock" not in availability
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
        "roast_level": None,  # 理由はモジュールdocstring参照(注文時に焙煎度合を選択する受注焙煎方式)
        "roast_hint": fields.get("お奨め焙煎度"),
        "roast_selectable": True,
        "post_processing_tags": parsed["post_processing_tags"],
        "blend_components": [],
        "flavor_notes": flavor_notes,
        "price": price,
        "weight_g": parse_roasted_weight(description),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": product_url,
    }


def parse_product_detail(url: str, category_hint: str = "") -> dict:
    soup = fetch_page(url)
    product = extract_jsonld_product(soup)
    if not product:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": "",
            "non_bean": True,
            "product_url": url,
        }
    return build_record(url, product, category_hint)


def scrape_category_list_page(cid: str) -> list[dict]:
    soup = fetch_page(f"{BASE_URL}/categories/{cid}")
    items = soup.select('a[href*="/items/"]')

    results = []
    seen_urls = set()
    for link_el in items:
        title_el = link_el.select_one('[class*="itemTitleText"]')
        if not title_el:
            continue
        href = link_el.get("href", "")
        product_url = href if href.startswith("http") else f"{BASE_URL}{href}"
        if product_url in seen_urls:
            continue
        seen_urls.add(product_url)
        results.append({"raw_name": title_el.get_text(strip=True), "product_url": product_url})
    return results


def scrape_all_products() -> tuple[list[dict], list[dict], list[dict]]:
    items_by_url: dict[str, dict] = {}
    for cid, category_hint in LIST_CATEGORIES.items():
        for item in scrape_category_list_page(cid):
            items_by_url.setdefault(item["product_url"], {**item, "category_hint": category_hint})
        time.sleep(CRAWL_DELAY_SECONDS)

    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    non_bean_records = []
    for product_url, item in items_by_url.items():
        prev = previous.get(product_url)
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = parse_product_detail(product_url, item["category_hint"])
            if detail.get("non_bean"):
                non_bean_records.append(detail)
            elif detail.get("is_flavored"):
                flavored_records.append(detail)
            else:
                records.append(detail)
            time.sleep(CRAWL_DELAY_SECONDS)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {product_url} ({e})")

    return records, flavored_records, non_bean_records


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = parse_product_detail(sys.argv[1])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        records, flavored_records, non_bean_records = scrape_all_products()
        output = {
            "shop": SHOP_INFO,
            "products": records,
            "flavored_products_excluded": flavored_records,
            "non_bean_products_excluded": non_bean_records,
        }
        with open("data_himonya.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"[done] {len(records)}件を data_himonya.json に出力しました"
              f"(フレーバーコーヒー{len(flavored_records)}件、"
              f"非コーヒー豆{len(non_bean_records)}件は別枠に分離)")
