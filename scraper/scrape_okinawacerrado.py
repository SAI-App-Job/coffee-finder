# -*- coding: utf-8 -*-
"""
scrape_okinawacerrado.py

沖縄セラードコーヒー(okinawa-cerrado.com、有限会社沖縄セラードコーヒー運営、
自家焙煎スペシャルティコーヒー専門店)の商品情報を取得する。カラーミー
ショップ(shop-pro.jp)。

【住所について】
特定商取引法ページ(https://okinawa-cerrado.com/?mode=sk)で実際に確認したところ
「郵便番号 901-2134 / 住所 沖縄県浦添市港川2丁目15番5-27号」であることを
確認した(2026-09時点、EUC-JPで直接デコードして確認)。候補リストにあった
実店舗「Beans Store」の住所(港川2丁目15-6 No.28)とは番地表記が異なるが、
特定商取引法ページに明記された販売業者(法人)の住所を正としてSHOP_INFO.address
に採用する(実店舗紹介ページは別ページ「?mode=f54」で紹介されているのみ)。

【文字コードについて】実データ確認済み: Content-Type: text/html; charset=EUC-JP。

【一覧ページについて】
`?mode=srh&keyword=&sort=n` で全カテゴリ横断の一覧(見出し"all items")が取得
できる(実データ確認済み、2026-09時点で全180件、10件超で自動的にページネーション
される)。テーマはoyamacoffee/rhizomagと同じ`prd-lst-unit`系(ハイフン区切り。
405coffeeの`prd_lst_unit`アンダースコア系とは異なる)。

【重量違いの重複について】
実データ確認済み: 大半の銘柄が800g/600g/400g/200g、または400g/300g/200g/100g
という複数サイズでそれぞれ独立した商品として登録されている(全180件→基準名で
グルーピングすると51銘柄)。商品名末尾の「(数字)g」+その内訳を示す括弧
「(200g×4bags)」等を除去した基準名でグルーピングし、最小重量を代表として
採用する(basecoffeeawajiと同じ考え方)。

【産地・精選方法について】
商品名は英語表記(例:"PERU SANTUARIO WASHED MEDIUMROAST 800g(200g×4bags)")。
coffee_parserの英語国名辞書(ORIGIN_COUNTRY_KEYWORDS_EN)・精選方法シノニム
(processing_method_synonyms.jsonのwashed/natural/honey等)で大半は検出できる。
ただし「COSTARICA」(スペース無し表記、実データ確認済み: 複数商品で確認)は
辞書の"costa rica"(スペース有り)に一致しないため、国名判定に失敗した場合の
フォールバックとして"costarica"→"costa rica"に正規化してから再判定する。

【焙煎度について】
商品名の英語表記(LIGHT ROAST/MEDIUM ROAST/DarkRoast等)はROAST_KEYWORDS
(日本語カタカナ用)の対象外のため検出されない。詳細ページの説明文
(div.product-order-exp)に【焙煎具合】欄があり「中煎り/Medium Roast」の
ように日本語表記が確認できる(実データ確認済み)。浅煎り/中煎り/中深煎り/深煎り
の4段階でROAST_LEVELSの8段階とは粒度が異なるため、roast_levelには入れず
roast_hintとして保持し、roast_selectable=Falseとする(405coffeeと同じ方針。
挽き方(豆のまま/粗挽き/中挽き/細挽き)は選べるが焙煎度自体は固定)。

【商品説明の構造】
div.product-order-exp内に【生産エリア】【生産者】【プロセス】【品種】【標高】
【焙煎具合】【TASTING NOTE/コーヒーの味の印象】ラベル付きの自由記述がある
(実データ確認済み)。精選方法欄はnormalize_processing_methodで正規化し、
生産エリア・生産者・品種・標高はfarm_noteに、TASTING NOTEはflavor_notesの
候補として使う。

【ブレンド・デカフェについて】
"SEASONS BLEND"「AUTUMN」「SUMMER」等・"DECAFE BLEND"はBLEND_KEYWORDSの
"blend"(大文字小文字無視)で正しくブレンド判定される(実データ確認済み)。
デカフェ単体("COSTARICA TARRAZU JAGUAR HONEY DECAF")はブレンドではなく
ストレートとして扱う。

【在庫について】
実データ確認済み: 全180件のうち144件がspan.prd-lst-soldoutで一覧段階から
SOLD OUT表示されている(COE入賞ロット・単一農園の少量マイクロロットが多い
店舗のため、売り切れ比率が高い)。一覧のSOLD OUT表示を構造的フラグとして使う
(oyamacoffee/rhizomagと同じ考え方)。

【非コーヒー豆商品の除外について】
実データ確認済み: 全180件の一覧に「ギフト」「ドリップ」「セット」「器具」
「GIFT」「DRIP」「SET」等に一致する商品名は見つからなかった(サイトナビには
ドリップバッグ/ギフトセット/珈琲器具のカテゴリ表示があるが、全件横断の
all items一覧には現れなかった)。念のためNON_BEAN_KEYWORDSでの除外は保持する。

robots.txt確認済み(2026-09時点): 標準的なshop-pro.jp系の記述で、User-agent: *
は/secure/と/cart/のみDisallow(他はAhrefsBot等SEO系ボット個別へのDisallow: /
のみ)。本スクレイパーが使う一覧・詳細ページは制限対象外。
"""

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from coffee_parser import (
    parse_product,
    normalize_processing_method,
    detect_stock_status,
    detect_country_name,
)
from previous_data import load_previous_products, is_unchanged

SHOP_INFO = {
    "name": "沖縄セラードコーヒー",
    "url": "https://okinawa-cerrado.com/",
    "platform": "カラーミーショップ(shop-pro.jp)",
    "address": "沖縄県浦添市港川2丁目15番5-27号",
    "prefecture": "沖縄県",
    "robots_txt_status": "実質許可(2026-09確認。/secure/と/cart/以外は制限なし。"
                          "他はSEO系ボットへの個別Disallow: /のみ)",
}

CRAWL_DELAY_SECONDS = 1
REQUEST_HEADERS = {
    "User-Agent": "CoffeeFinderBot/0.1 (+contact: your-contact-info-here)"
}

BASE_URL = "https://okinawa-cerrado.com/"
LIST_BASE_URL = "https://okinawa-cerrado.com/?mode=srh&keyword=&sort=n"

NON_BEAN_KEYWORDS = ["ギフト", "gift", "ドリップバッグ", "drip", "セット", "set", "器具"]

COLORME_JSON_PATTERN = re.compile(r"var\s+Colorme\s*=\s*(\{.*\});", re.DOTALL)
# 商品名末尾の重量+任意の内訳括弧(例:「800g(200g×4bags)」「200g」)を除去して
# 基準名を求める。全角×・半角xいずれの区切りにも対応する。
TRAILING_WEIGHT_PATTERN = re.compile(
    r"[\s　]*(\d+)\s*[gｇ]\s*(\([\d\s]+[gｇ][×xX][\d\s]+ba*gs?\))?\s*\Z"
)
LABEL_PATTERN = re.compile(r"【([^】]+)】\s*([^\n【]*)")
TASTING_HEADER_PATTERN = re.compile(r"TASTING NOTE[^\n]*\n(.*?)(?:\n\n|\Z)", re.DOTALL)


def fetch_page(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-jp"  # 実データ確認済み(Content-Type: text/html; charset=EUC-JP)
    soup = BeautifulSoup(resp.text, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return soup


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


def normalize_base_name(title: str) -> str:
    return TRAILING_WEIGHT_PATTERN.sub("", title).strip()


def extract_weight(title: str) -> int | None:
    m = TRAILING_WEIGHT_PATTERN.search(title)
    return int(m.group(1)) if m else None


def scrape_list_page(page: int) -> list[dict]:
    url = LIST_BASE_URL if page == 1 else f"{LIST_BASE_URL}&page={page}"
    soup = fetch_page(url)
    items = []
    for li in soup.select("li.prd-lst-unit"):
        name_el = li.select_one(".prd-lst-name a")
        if not name_el:
            continue
        title = name_el.get_text(strip=True)
        if any(kw.lower() in title.lower() for kw in NON_BEAN_KEYWORDS):
            continue
        href = name_el.get("href", "")
        product_url = f"{BASE_URL}{href}" if href.startswith("?") else href
        out_of_stock = bool(li.select_one(".prd-lst-soldout"))
        items.append({
            "raw_name": title,
            "product_url": product_url,
            "out_of_stock": out_of_stock,
        })
    return items


def pick_canonical_items(items: list[dict]) -> list[dict]:
    by_base_name: dict[str, tuple[int, dict]] = {}
    for item in items:
        base = normalize_base_name(item["raw_name"])
        weight = extract_weight(item["raw_name"])
        weight_key = weight if weight is not None else float("inf")
        existing = by_base_name.get(base)
        if existing is None or weight_key < existing[0]:
            by_base_name[base] = (weight_key, item)
    return [item for _weight, item in by_base_name.values()]


def parse_description_fields(description_text: str) -> dict:
    labels = {}
    for label, value in LABEL_PATTERN.findall(description_text):
        value = value.strip()
        if value:
            labels[label] = value

    tasting_m = TASTING_HEADER_PATTERN.search(description_text)
    tasting_note = tasting_m.group(1).strip() if tasting_m else None

    roast_hint = None
    if labels.get("焙煎具合"):
        # 「中煎り/Medium Roast」のように日本語部分が先頭にある
        roast_hint = labels["焙煎具合"].split("/")[0].strip() or None

    return {"labels": labels, "tasting_note": tasting_note, "roast_hint": roast_hint}


def detect_country_with_fallback(title: str) -> tuple[str | None, str | None]:
    # 実データ確認済み: 「JAPAN FINCA AGARIBARU OKINAWA100%」1件のみ、沖縄県内で
    # 栽培された国産(沖縄産)豆。coffee_parserの国名辞書に"japan"は無く(他店舗で
    # "Japan Blend"等の誤爆リスクがあるため辞書には追加せず、この店舗限定でローカルに
    # 判定する)。
    if "japan" in title.lower() and "okinawa" in title.lower():
        return "日本(沖縄県)", "country_name"

    country = detect_country_name(title)
    if country:
        return country, "country_name"
    # 「COSTARICA」(スペース無し)は英語国名辞書の"costa rica"に一致しないための
    # フォールバック(実データ確認済み: 複数商品で確認)
    normalized = re.sub(r"(?i)costarica", "costa rica", title)
    if normalized != title:
        country = detect_country_name(normalized)
        if country:
            return country, "country_name"
    return None, None


def build_record(item: dict) -> dict | None:
    title = item["raw_name"]
    parsed = parse_product(title)

    if parsed["is_flavored"]:
        return {
            "shop_name": SHOP_INFO["name"],
            "raw_name": title,
            "category": "フレーバー",
            "is_flavored": True,
            "flavor_name": parsed["flavor_name"],
            "price": None,
            "product_url": item["product_url"],
        }

    if not parsed["origin_country"] and parsed["category"] != "ブレンド":
        country, source = detect_country_with_fallback(title)
        if country:
            parsed["origin_country"] = country
            parsed["origin_source"] = source

    soup = fetch_page(item["product_url"])
    colorme_product = extract_colorme_product(soup) or {}
    price = colorme_product.get("sales_price_including_tax") or colorme_product.get("sales_price")

    desc_el = soup.select_one("div.product-order-exp")
    desc_text = desc_el.get_text() if desc_el else ""
    fields = parse_description_fields(desc_text)
    labels = fields["labels"]

    if labels.get("プロセス") and not parsed["processing_method"]:
        parsed["processing_method"] = normalize_processing_method(labels["プロセス"])

    farm_note_parts = []
    if labels.get("生産エリア"):
        farm_note_parts.append(f"生産エリア: {labels['生産エリア']}")
    if labels.get("生産者"):
        farm_note_parts.append(f"生産者: {labels['生産者']}")
    if labels.get("品種"):
        farm_note_parts.append(f"品種: {labels['品種']}")
    if labels.get("標高"):
        farm_note_parts.append(f"標高: {labels['標高']}")
    farm_note = "、".join(farm_note_parts) if farm_note_parts else None

    stock_status = detect_stock_status(title, item.get("out_of_stock", False))

    return {
        "shop_name": SHOP_INFO["name"],
        "raw_name": title,
        "category": parsed["category"],
        "origin_country": parsed["origin_country"],
        "origin_source": parsed["origin_source"],
        "designated_brand": parsed["designated_brand"],
        "processing_method": parsed["processing_method"],
        "grade": parsed["grade"],
        "roast_level": None,  # 商品名の英語ロースト表記はROAST_KEYWORDS対象外(理由はdocstring参照)
        "roast_hint": fields["roast_hint"],
        "roast_selectable": False,  # 挽き方は選べるが焙煎度自体は固定(実データ確認済み)
        "post_processing_tags": parsed["post_processing_tags"],
        "farm_note": farm_note,
        "flavor_notes": fields["tasting_note"],
        "blend_components": [],
        "price": price,
        "weight_g": extract_weight(title),
        "stock_status": stock_status,
        "out_of_stock": stock_status != "販売中",
        "product_url": item["product_url"],
    }


MAX_PAGES = 30


def scrape_all_products() -> tuple[list[dict], list[dict]]:
    all_items = []
    page = 1
    while page <= MAX_PAGES:
        items = scrape_list_page(page)
        if not items:
            break
        all_items.extend(items)
        page += 1
        time.sleep(CRAWL_DELAY_SECONDS)

    canonical_items = pick_canonical_items(all_items)
    previous = load_previous_products(SHOP_INFO["name"])

    records = []
    flavored_records = []
    for item in canonical_items:
        prev = previous.get(item["product_url"])
        if is_unchanged(prev, raw_name=item["raw_name"]):
            records.append(prev)
            continue

        try:
            detail = build_record(item)
        except requests.RequestException as e:
            print(f"[warn] 詳細ページ取得失敗: {item['product_url']} ({e})")
            continue
        if detail is None:
            continue
        if detail.get("is_flavored"):
            flavored_records.append(detail)
        else:
            records.append(detail)
        time.sleep(CRAWL_DELAY_SECONDS)

    return records, flavored_records


if __name__ == "__main__":
    records, flavored_records = scrape_all_products()
    output = {
        "shop": SHOP_INFO,
        "products": records,
        "flavored_products_excluded": flavored_records,
    }
    with open("data_okinawacerrado.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(records)}件を data_okinawacerrado.json に出力しました"
          f"(フレーバーコーヒー{len(flavored_records)}件は別枠に分離)")
